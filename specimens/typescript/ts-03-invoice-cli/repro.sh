#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

NODE_FLAGS=""
if ! node -e 'const [a,b]=process.versions.node.split(".").map(Number);process.exit(a>23||(a===23&&b>=6)?0:1)'; then
  NODE_FLAGS="--experimental-strip-types --no-warnings"
fi
mkdir -p out

NODE_FLAGS="$NODE_FLAGS" python3 - <<'PY'
import hashlib, json, os, re, shutil, subprocess, sys

HERE = os.getcwd()
OUT = os.path.join(HERE, "out", "repro")
shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(OUT)
NODE = ["node", *os.environ.get("NODE_FLAGS", "").split(), os.path.join(HERE, "invoice.ts")]
results = {}


def fixture(name, items):
    path = os.path.join(OUT, name)
    with open(path, "w") as f:
        json.dump(items, f)
    return path


def invoice(*args, cwd=OUT):
    p = subprocess.run([*NODE, *args], capture_output=True, text=True, cwd=cwd, timeout=60)
    return p.returncode, p.stdout, p.stderr.strip()


def row(text, label):
    m = re.search(rf"^{re.escape(label)}[^:]*:\s+(-?[\d.]+|NaN)\s*$", text, re.M)
    return m.group(1) if m else None


def case(did, name, fn):
    try:
        ok, evidence = fn()
    except Exception as exc:
        ok, evidence = False, f"harness error: {exc!r}"
    results[did] = ok
    print(f"{'[REPRODUCED]' if ok else '[NOT REPRODUCED]'} {did} {name}: {evidence}", flush=True)


def float_subtotal():
    items = fixture("dimes.json", [{"sku": f"D{i}", "unitPrice": 0.1, "quantity": 1} for i in range(3)])
    code, out, _ = invoice("--items", items, "--json")
    sub = json.loads(out)["subtotal"]
    return code == 0 and sub != 0.3, f"3 x 0.10 -> JSON subtotal {sub!r}"


def tax_line_mismatch():
    items = fixture("hundred.json", [{"sku": "SVC", "unitPrice": 100, "quantity": 1}])
    code, out, _ = invoice("--items", items, "--tax", "10", "--discount", "10")
    sub, disc, tax, total = (float(row(out, l)) for l in ("Subtotal", "Discount", "Tax", "Total"))
    return code == 0 and round(sub + disc + tax, 2) != total, f"printed {sub} {disc:+} + tax {tax} = {sub + disc + tax:.2f} but Total {total}"


def full_discount_nan():
    code, out, _ = invoice("--items", os.path.join(HERE, "items.json"), "--tax", "10", "--discount", "100")
    line = next((l for l in out.splitlines() if l.startswith("Effective tax rate")), "")
    return code == 0 and "NaN" in line, f"--discount 100 -> {line!r}"


def negative_quantity():
    items = fixture("negative.json", [{"sku": "A", "unitPrice": 10, "quantity": 2}, {"sku": "B", "unitPrice": 50, "quantity": -3}])
    code, out, _ = invoice("--items", items, "--json")
    sub = json.loads(out)["subtotal"]
    return code == 0 and sub < 0, f"quantity -3 accepted, exit {code}, subtotal {sub}"


def page_footer_oob():
    items = fixture("twelve.json", [{"sku": f"SKU-{i:02d}", "unitPrice": 1, "quantity": 1} for i in range(12)])
    code, _, err = invoice("--items", items)
    return code != 0 and "undefined" in err, f"12 items (2 pages) -> exit {code}: {err!r}"


def md5_invoice_id():
    a = fixture("a.json", [{"sku": "A", "unitPrice": 5, "quantity": 1}])
    b = fixture("b.json", [{"sku": "B", "unitPrice": 999, "quantity": 9}])
    _, out_a, _ = invoice("--items", a, "--customer", "Globex", "--date", "2026-10-01", "--json")
    _, out_b, _ = invoice("--items", b, "--customer", "Globex", "--date", "2026-10-01", "--json")
    id_a, id_b = json.loads(out_a)["id"], json.loads(out_b)["id"]
    guess = "INV-" + hashlib.md5(b"Globex:2026-10-01").hexdigest()[:12].upper()
    return id_a == guess == id_b, f"id {id_a} == md5('Globex:2026-10-01') prefix; a different invoice got {id_b}"


def out_command_injection():
    work = os.path.join(OUT, "inject")
    os.makedirs(work)
    code, _, err = invoice("--items", os.path.join(HERE, "items.json"), "--out", "inv.txt;touch pwned.flag", cwd=work)
    flag = os.path.exists(os.path.join(work, "pwned.flag"))
    return flag, f"--out 'inv.txt;touch pwned.flag' (exit {code}) -> pwned.flag created={flag}"


def bad_item_skipped():
    items = fixture("mixed.json", [{"sku": "OK", "unitPrice": 10, "quantity": 1}, {"sku": "LAPTOP", "unitPrice": "1299.00", "quantity": 1}])
    code, out, err = invoice("--items", items)
    return code == 0 and "LAPTOP" not in out and err == "", f"exit {code}, stderr {err!r}, LAPTOP missing, Subtotal {row(out, 'Subtotal')}"


def discount_over_100():
    code, out, _ = invoice("--items", os.path.join(HERE, "items.json"), "--discount", "150")
    total = float(row(out, "Total"))
    return code == 0 and total < 0, f"--discount 150 -> exit {code}, Total {total}"


def tax_truncated():
    items = fixture("one.json", [{"sku": "W", "unitPrice": 19.99, "quantity": 1}])
    code, out, _ = invoice("--items", items, "--tax", "10", "--json")
    tax = json.loads(out)["tax"]
    return code == 0 and tax == 1.99, f"10% of 19.99 (1.999) -> tax {tax}, expected 2.00"


case("TS03-D01", "float_subtotal", float_subtotal)
case("TS03-D02", "tax_line_mismatch", tax_line_mismatch)
case("TS03-D03", "full_discount_nan", full_discount_nan)
case("TS03-D04", "negative_quantity", negative_quantity)
case("TS03-D05", "page_footer_oob", page_footer_oob)
case("TS03-D06", "md5_invoice_id", md5_invoice_id)
case("TS03-D07", "out_command_injection", out_command_injection)
case("TS03-D08", "bad_item_skipped", bad_item_skipped)
case("TS03-D09", "discount_over_100", discount_over_100)
case("TS03-D10", "tax_truncated", tax_truncated)

expected = {d["id"] for d in json.load(open("DEFECTS.json"))["defects"]}
missing = expected - set(results)
for did in sorted(missing):
    print(f"[NOT REPRODUCED] {did} missing_case: repro.sh has no case for this defect")
ok = not missing and all(results.get(d) for d in expected)
print(f"{sum(1 for d in expected if results.get(d))}/{len(expected)} defects reproduced")
sys.exit(0 if ok else 1)
PY
