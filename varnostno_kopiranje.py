#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import yaml
import smtplib
import paramiko
import boto3
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, timedelta
from jsonschema import validate, ValidationError
from pomocne_funkcije import *


class VarnostnoKopiranje:
    def __init__(self, pot_konfiguracije):
        self.pot_konfiguracije = pot_konfiguracije
        self.config = None
        self.ime_dnevnika = None

    def nalozi_konfiguracijo(self):
        try:
            with open(self.pot_konfiguracije, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)

            with open('nastavitve/shema.yaml', 'r', encoding='utf-8') as f:
                shema = yaml.safe_load(f)

            validate(instance=self.config, schema=shema)

            print(" Konfiguracija uspešno naložena in validirana")
            return True

        except FileNotFoundError:
            print(f"Datoteka {self.pot_konfiguracije} ne obstaja!")
            return False
        except ValidationError as e:
            print(f"Napaka v konfiguraciji: {e.message}")
            return False
        except Exception as e:
            print(f"Napaka pri nalaganju konfiguracije: {str(e)}")
            return False

    def preveri_zahteve(self):
        manjkajoča_orodja = preveri_orodja()

        if manjkajoča_orodja:
            sporocilo = f"Manjkajoča orodja: {', '.join(manjkajoča_orodja)}"
            print(f"✗ {sporocilo}")
            zapisi_v_dnevnik(self.ime_dnevnika, sporocilo, "NAPAKA")
            return False

        print("Vsa potrebna orodja so nameščena")
        return True

    def ustvari_varnostno_kopijo(self):
        try:
            casovni_zig = ustvari_časovni_zig()

            baza = self.config['baza_podatkov']
            pot_varnostne_kopije = self.config['poti']['varnostne_kopije']

            if not os.path.exists(pot_varnostne_kopije):
                os.makedirs(pot_varnostne_kopije)

            ime_datoteke = f"{baza['ime_baze']}_backup_{casovni_zig}.sql"
            polna_pot = os.path.join(pot_varnostne_kopije, ime_datoteke)

            ukaz = [
                'mysqldump',
                f"--host={baza['gostitelj']}",
                f"--port={baza['vrata']}",
                f"--user={baza['uporabnisko_ime']}",
                f"--password={baza['geslo']}",
                '--single-transaction',
                '--quick',
                '--lock-tables=false',
                baza['ime_baze']
            ]

            zapisi_v_dnevnik(self.ime_dnevnika,
                             f"Začenjam varnostno kopiranje baze {baza['ime_baze']}")

            with open(polna_pot, 'w') as f:
                rezultat = subprocess.run(ukaz, stdout=f, stderr=subprocess.PIPE)

            if rezultat.returncode != 0:
                raise Exception(f"Mysqldump napaka: {rezultat.stderr.decode()}")

            velikost = velikost_datoteke_berljivo(polna_pot)
            zapisi_v_dnevnik(self.ime_dnevnika,
                             f"Varnostna kopija ustvarjena: {ime_datoteke} ({velikost})")

            return polna_pot

        except Exception as e:
            zapisi_v_dnevnik(self.ime_dnevnika,
                             f"Napaka pri ustvarjanju varnostne kopije: {str(e)}",
                             "napaka")
            return None

    def sifriraj_datoteko(self, pot_datoteke):
        try:
            email_prejemnika = self.config['gpg']['email_prejemnika']
            pot_sifrirane = f"{pot_datoteke}.gpg"

            zapisi_v_dnevnik(self.ime_dnevnika,
                             f"Šifriram datoteko za prejemnika: {email_prejemnika}")
            ukaz = [
                'gpg',
                '--encrypt',
                '--recipient', email_prejemnika,
                '--trust-model', 'always',
                '--output', pot_sifrirane,
                pot_datoteke
            ]

            rezultat = subprocess.run(ukaz, capture_output=True)

            if rezultat.returncode != 0:
                raise Exception(f"GPG napaka: {rezultat.stderr.decode()}")

            os.remove(pot_datoteke)

            velikost = velikost_datoteke_berljivo(pot_sifrirane)
            zapisi_v_dnevnik(self.ime_dnevnika,
                             f"Datoteka šifrirana: {os.path.basename(pot_sifrirane)} ({velikost})")

            return pot_sifrirane

        except Exception as e:
            zapisi_v_dnevnik(self.ime_dnevnika,
                             f"Napaka pri šifriranju: {str(e)}",
                             "NAPAKA")
            return None

    def poslji_po_emailu(self, pot_datoteke):
        try:
            if not self.config['distribucija']['email']['omogoceno']:
                return True

            email_config = self.config['distribucija']['email']

            zapisi_v_dnevnik(self.ime_dnevnika,
                             f"Pošiljam e-mail na {email_config['za']}")

            sporocilo = MIMEMultipart()
            sporocilo['From'] = email_config['od']
            sporocilo['To'] = email_config['za']
            sporocilo['Subject'] = f"Varnostna kopija MySQL - {datetime.now().strftime('%Y-%m-%d %H:%M')}"

            with open(pot_datoteke, 'rb') as f:
                del_priloge = MIMEBase('application', 'octet-stream')
                del_priloge.set_payload(f.read())
                encoders.encode_base64(del_priloge)
                del_priloge.add_header(
                    'Content-Disposition',
                    f'attachment; filename={os.path.basename(pot_datoteke)}'
                )
                sporocilo.attach(del_priloge)

            with smtplib.SMTP(email_config['smtp_streznik'],
                              email_config['smtp_vrata']) as streznik:
                streznik.starttls()
                streznik.login(email_config['uporabnisko_ime'],
                               email_config['geslo'])
                streznik.send_message(sporocilo)

            zapisi_v_dnevnik(self.ime_dnevnika,
                             "E-mail uspešno poslan")
            return True

        except Exception as e:
            zapisi_v_dnevnik(self.ime_dnevnika,
                             f"Napaka pri pošiljanju e-maila: {str(e)}",
                             "NAPAKA")
            return False

    def poslji_na_sftp(self, pot_datoteke):
        try:
            if not self.config['distribucija']['sftp']['omogoceno']:
                return True

            sftp_config = self.config['distribucija']['sftp']

            zapisi_v_dnevnik(self.ime_dnevnika,
                             f"Nalagam na SFTP strežnik {sftp_config['gostitelj']}")

            transport = paramiko.Transport((sftp_config['gostitelj'],
                                            sftp_config['vrata']))
            transport.connect(username=sftp_config['uporabnisko_ime'],
                              password=sftp_config['geslo'])

            sftp = paramiko.SFTPClient.from_transport(transport)
            oddaljena_pot = os.path.join(sftp_config['pot'],
                                         os.path.basename(pot_datoteke))
            sftp.put(pot_datoteke, oddaljena_pot)

            sftp.close()
            transport.close()

            zapisi_v_dnevnik(self.ime_dnevnika,
                             f"Datoteka naložena na SFTP: {oddaljena_pot}")
            return True

        except Exception as e:
            zapisi_v_dnevnik(self.ime_dnevnika,
                             f"Napaka pri SFTP nalaganju: {str(e)}",
                             "NAPAKA")
            return False

    def poslji_na_aws_s3(self, pot_datoteke):
        try:
            if not self.config['distribucija']['aws_s3']['omogoceno']:
                return True

            s3_config = self.config['distribucija']['aws_s3']

            zapisi_v_dnevnik(self.ime_dnevnika,
                             f"Nalagam na AWS S3 vedro {s3_config['vedro']}")
            s3 = boto3.client(
                's3',
                region_name=s3_config['regija'],
                aws_access_key_id=s3_config['dostopni_kljuc'],
                aws_secret_access_key=s3_config['skrivni_kljuc']
            )
            ime_kljuca = os.path.basename(pot_datoteke)
            s3.upload_file(pot_datoteke, s3_config['vedro'], ime_kljuca)

            zapisi_v_dnevnik(self.ime_dnevnika,
                             f"Datoteka naložena na S3: {ime_kljuca}")
            return True

        except Exception as e:
            zapisi_v_dnevnik(self.ime_dnevnika,
                             f"Napaka pri S3 nalaganju: {str(e)}",
                             "napaka")
            return False

    def rotiraj_varnostne_kopije(self):
        try:
            pot = self.config['poti']['varnostne_kopije']
            rotacija = self.config['rotacija']

            zapisi_v_dnevnik(self.ime_dnevnika,
                             "Začenjam rotacijo varnostnih kopij")

            datoteke = []
            for ime in os.listdir(pot):
                if ime.endswith('.gpg'):
                    polna_pot = os.path.join(pot, ime)
                    cas = os.path.getmtime(polna_pot)
                    datoteke.append((polna_pot, cas))

            datoteke.sort(key=lambda x: x[1], reverse=True)

            zdaj = datetime.now()
            izbrisane = 0

            for pot_datoteke, cas_datoteke in datoteke:
                cas = datetime.fromtimestamp(cas_datoteke)
                starost = (zdaj - cas).days

                ohrani = False

                if starost < rotacija['dnevne']:
                    ohrani = True
                elif starost < rotacija['tedenske'] * 7 and cas.weekday() == 0:
                    ohrani = True
                elif starost < rotacija['mesecne'] * 30 and cas.day == 1:
                    ohrani = True

                if not ohrani:
                    os.remove(pot_datoteke)
                    izbrisane += 1

            zapisi_v_dnevnik(self.ime_dnevnika,
                             f"Rotacija končana. Izbrisano {izbrisane} starih kopij")

        except Exception as e:
            zapisi_v_dnevnik(self.ime_dnevnika,
                             f"Napaka pri rotaciji: {str(e)}",
                             "NAPAKA")

    def izvedi(self):
        # Nastavi dnevnik
        pot_dnevnika = self.config['poti']['dnevniki']
        self.ime_dnevnika = nastavi_dnevnik(pot_dnevnika)

        zapisi_v_dnevnik(self.ime_dnevnika, 
                        "═══════════════════════════════════════")
        zapisi_v_dnevnik(self.ime_dnevnika, 
                        "Začenjam postopek varnostnega kopiranja")
        zapisi_v_dnevnik(self.ime_dnevnika, 
                        "═══════════════════════════════════════")

        if not self.preveri_zahteve():
            return False

        pot_kopije = self.ustvari_varnostno_kopijo()
        if not pot_kopije:
            return False


        pot_sifrirane = self.sifriraj_datoteko(pot_kopije)
        if not pot_sifrirane:
            return False


        uspeh_email = self.poslji_po_emailu(pot_sifrirane)
        uspeh_sftp = self.poslji_na_sftp(pot_sifrirane)
        uspeh_s3 = self.poslji_na_aws_s3(pot_sifrirane)

        # Rotiraj stare kopije
        self.rotiraj_varnostne_kopije()

        zapisi_v_dnevnik(self.ime_dnevnika, 
                        "═══════════════════════════════════════")
        zapisi_v_dnevnik(self.ime_dnevnika, 
                        "Postopek varnostnega kopiranja končan")
        zapisi_v_dnevnik(self.ime_dnevnika, 
                        "═══════════════════════════════════════")

        return True


def main():
    if len(sys.argv) > 1:
        pot_konfiguracije = sys.argv[1]
    else:
        pot_konfiguracije = 'nastavitve/konfiguracija.yaml'

    vk = VarnostnoKopiranje(pot_konfiguracije)

    if not vk.nalozi_konfiguracijo():
        sys.exit(1)

    if vk.izvedi():
        print("\nVarnostno kopiranje uspešno zaključeno!")
        sys.exit(0)
    else:
        print("\nVarnostno kopiranje neuspešno!")
        sys.exit(1)


if __name__ == "__main__":
    main()
