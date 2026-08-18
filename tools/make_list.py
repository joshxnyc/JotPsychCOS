"""Generate a dormant list of any size, to test behaviour at real scale.

    python tools/make_list.py 15000 > inbox/dormant.csv

The brief says we do not get the real list, so this makes one with the same
three fields and the same messiness: consumer and practice email domains, names
written five different ways, missing mobiles, duplicates. Nothing here matches a
real person — these are generated names, so the registry correctly fails to
resolve most of them, which is the honest yield.
"""
import csv, random, sys

FIRST = ("Sarah Michael Maria David Jennifer Robert Lisa Daniel Priya Marcus Amara Yuki "
         "Tomas Nadia Elias Sofia Colm Leilani Hyun-Woo Fatima Gabriel Rebecca Aaron "
         "Ingrid Odalys Cassius Anneliese Bartholomew Thaddeus Marisol").split()
LAST = ("Chen Garcia Johnson Goldberg Rivera Delgado Nguyen Cohen Patel Blake Osei Tanaka "
        "Lindqvist Petrov Mbeki Duarte Fitzgerald Kahananui Park Al-Rashid Santos Sterling "
        "Whitcombe Halvorsen Fernandez Brightwater Sorokin Quintanilla Okonkwo Vantongeren").split()
WORD1 = "harbor river canyon meadow north south lake stone bright quiet cedar summit island crescent".split()
WORD2 = "point bend oaks lark star ridge grove field haven creek gate path shore bay".split()
KIND = "behavioral psychiatry counseling therapy mindhealth psychology wellness".split()
CONSUMER = "gmail.com yahoo.com hotmail.com outlook.com icloud.com aol.com".split()
CRED = ["", "", "", ", LCSW", ", MD", ", PMHNP", ", PsyD", ", LPC"]


def rows(n: int, seed: int = 7):
    r = random.Random(seed)
    seen = set()
    while len(seen) < n:
        f, l = r.choice(FIRST), r.choice(LAST)
        if r.random() < 0.55:
            dom = f"{r.choice(WORD1)}{r.choice(WORD2)}{r.choice(KIND)}.com"
            local = r.choice([f"{f[0]}.{l}", f"{f}.{l}", f"{f[0]}{l}", f"dr{l}"]).lower()
        else:
            dom = r.choice(CONSUMER)
            local = f"{f}{l}{r.randint(1, 99)}".lower()
        email = f"{local}@{dom}"
        if email in seen:
            continue
        seen.add(email)
        name = r.choice([f"{f} {l}", f"{f} {l}{r.choice(CRED)}", f"{l}, {f}",
                         f"Dr. {f} {l}", f"{f[0]}. {l}"])
        mobile = "" if r.random() < 0.07 else (
            f"+1 {r.choice(('212','646','415','305','617','512','206','312','404','702'))} "
            f"555 {r.randint(1000, 9999)}")
        yield {"name": name, "email": email, "mobile": mobile}


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 15000
    w = csv.DictWriter(sys.stdout, fieldnames=["name", "email", "mobile"])
    w.writeheader()
    for row in rows(n):
        w.writerow(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
