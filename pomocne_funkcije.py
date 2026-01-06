#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import logging
from datetime import datetime
import pytz


def nastavi_dnevnik(pot_dnevnika):

    if not os.path.exists(pot_dnevnika):
        os.makedirs(pot_dnevnika)

    cas = datetime.now(pytz.UTC).strftime("%Y%m%d_%H%M%S")
    ime_datoteke = os.path.join(pot_dnevnika, f"dnevnik_{cas}.json")

    return ime_datoteke


def zapisi_v_dnevnik(ime_datoteke, sporocilo, raven="INFO", dodatni_podatki=None):
    vnos = {
        "casovni_zig": datetime.now(pytz.UTC).isoformat(),
        "raven": raven,
        "sporocilo": sporocilo
    }

    if dodatni_podatki:
        vnos["dodatni_podatki"] = dodatni_podatki

    try:
        if os.path.exists(ime_datoteke):
            with open(ime_datoteke, 'r', encoding='utf-8') as f:
                vnosi = json.load(f)
        else:
            vnosi = []

        vnosi.append(vnos)

        with open(ime_datoteke, 'w', encoding='utf-8') as f:
            json.dump(vnosi, f, ensure_ascii=False, indent=2)

        print(f"[{vnos['raven']}] {vnos['sporocilo']}")

    except Exception as e:
        print(f"Napaka pri pisanju v dnevnik: {str(e)}")


def preveri_orodja():
    orodja = ['mysqldump', 'gpg', 'mysql']
    manjkajoča = []

    for orodje in orodja:
        if os.system(f"which {orodje} > /dev/null 2>&1") != 0:
            manjkajoča.append(orodje)

    return manjkajoča


def ustvari_časovni_zig():
    zdaj = datetime.now(pytz.UTC)
    return zdaj.strftime("%Y%m%d_%H%M%S_%Z")


def velikost_datoteke_berljivo(pot):
    velikost = os.path.getsize(pot)

    for enota in ['B', 'KB', 'MB', 'GB']:
        if velikost < 1024.0:
            return f"{velikost:.2f} {enota}"
        velikost /= 1024.0

    return f"{velikost:.2f} TB"
