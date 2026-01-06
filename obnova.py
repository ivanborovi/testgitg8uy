#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import yaml
from pomocne_funkcije import *


class ObnavljanjeBaze:
    def __init__(self, pot_konfiguracije):
        self.pot_konfiguracije = pot_konfiguracije
        self.config = None
        self.ime_dnevnika = None

    def nalozi_konfiguracijo(self):
        try:
            with open(self.pot_konfiguracije, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
            print("Konfiguracija naložena")
            return True
        except Exception as e:
            print(f"Napaka pri nalaganju konfiguracije: {str(e)}")
            return False

    def desifriraj_datoteko(self, pot_sifrirane_datoteke):
        try:
            if not pot_sifrirane_datoteke.endswith('.gpg'):
                print("✗ Datoteka ni šifrirana (ni .gpg)")
                return None

            pot_desifrirane = pot_sifrirane_datoteke[:-4]  # Odstrani .gpg

            zapisi_v_dnevnik(self.ime_dnevnika,
                             f"Dešifriram datoteko: {os.path.basename(pot_sifrirane_datoteke)}")

            ukaz = [
                'gpg',
                '--decrypt',
                '--output', pot_desifrirane,
                pot_sifrirane_datoteke
            ]

            rezultat = subprocess.run(ukaz, capture_output=True)

            if rezultat.returncode != 0:
                raise Exception(f"GPG napaka: {rezultat.stderr.decode()}")

            zapisi_v_dnevnik(self.ime_dnevnika,
                             f"Datoteka dešifrirana: {os.path.basename(pot_desifrirane)}")

            return pot_desifrirane

        except Exception as e:
            zapisi_v_dnevnik(self.ime_dnevnika,
                             f"Napaka pri dešifriranju: {str(e)}",
                             "NAPAKA")
            return None

    def obnovi_bazo(self, pot_sql_datoteke, ime_testne_baze=None):
        try:
            baza = self.config['baza_podatkov']

            if not ime_testne_baze:
                ime_testne_baze = f"{baza['ime_baze']}_test"

            zapisi_v_dnevnik(self.ime_dnevnika,
                             f"Obnavljam bazo v: {ime_testne_baze}")

            ukaz_ustvarjanja = [
                'mysql',
                f"--host={baza['gostitelj']}",
                f"--port={baza['vrata']}",
                f"--user={baza['uporabnisko_ime']}",
                f"--password={baza['geslo']}",
                '-e',
                f"CREATE DATABASE IF NOT EXISTS {ime_testne_baze};"
            ]

            rezultat = subprocess.run(ukaz_ustvarjanja, capture_output=True)

            if rezultat.returncode != 0:
                raise Exception(f"Napaka pri ustvarjanju baze: {rezultat.stderr.decode()}")

            ukaz_uvoza = [
                'mysql',
                f"--host={baza['gostitelj']}",
                f"--port={baza['vrata']}",
                f"--user={baza['uporabnisko_ime']}",
                f"--password={baza['geslo']}",
                ime_testne_baze
            ]

            with open(pot_sql_datoteke, 'r') as f:
                rezultat = subprocess.run(ukaz_uvoza, stdin=f, capture_output=True)

            if rezultat.returncode != 0:
                raise Exception(f"Napaka pri uvozu: {rezultat.stderr.decode()}")

            zapisi_v_dnevnik(self.ime_dnevnika,
                             f"Baza uspešno obnovljena v: {ime_testne_baze}")

            return True

        except Exception as e:
            zapisi_v_dnevnik(self.ime_dnevnika,
                             f"Napaka pri obnavljanju baze: {str(e)}",
                             "NAPAKA")
            return False

    def izvedi_obnovo(self, pot_varnostne_kopije, ime_testne_baze=None):

        pot_dnevnika = self.config['poti']['dnevniki']
        self.ime_dnevnika = nastavi_dnevnik(pot_dnevnika)

        zapisi_v_dnevnik(self.ime_dnevnika)
        zapisi_v_dnevnik(self.ime_dnevnika,
                         "Začenjam postopek obnavljanja baze")
        zapisi_v_dnevnik(self.ime_dnevnika)

        pot_sql = self.desifriraj_datoteko(pot_varnostne_kopije)
        if not pot_sql:
            return False

        uspeh = self.obnovi_bazo(pot_sql, ime_testne_baze)

        if os.path.exists(pot_sql):
            os.remove(pot_sql)
            zapisi_v_dnevnik(self.ime_dnevnika,
                             "Dešifrirana datoteka izbrisana iz varnostnih razlogov")

        zapisi_v_dnevnik(self.ime_dnevnika)
        zapisi_v_dnevnik(self.ime_dnevnika,
                         "Postopek obnavljanja koncan")
        zapisi_v_dnevnik(self.ime_dnevnika)

        return uspeh


def main():
    if len(sys.argv) < 2:
        print("Uporaba: python3 obnova.py <pot_do_varnostne_kopije.gpg> [ime_testne_baze]")
        sys.exit(1)

    pot_varnostne_kopije = sys.argv[1]
    ime_testne_baze = sys.argv[2] if len(sys.argv) > 2 else None

    ob = ObnavljanjeBaze('nastavitve/konfiguracija.yaml')

    if not ob.nalozi_konfiguracijo():
        sys.exit(1)

    if ob.izvedi_obnovo(pot_varnostne_kopije, ime_testne_baze):
        print("\n Obnova uspesna")
        sys.exit(0)
    else:
        print("\nnapaka")
        sys.exit(1)


if __name__ == "__main__":
    main()
