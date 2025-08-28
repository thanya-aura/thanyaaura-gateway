
import os, zipfile, argparse

def pack(src_folder, out_zip):
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(src_folder):
            for fn in files:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, src_folder)
                zf.write(full, rel)

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Pack Microsoft 365 appPackage to .zip")
    p.add_argument("--src", required=True, help="Path to appPackage folder")
    p.add_argument("--out", required=True, help="Path to output zip file")
    args = p.parse_args()
    pack(args.src, args.out)
    print(f"Packed {args.src} -> {args.out}")
