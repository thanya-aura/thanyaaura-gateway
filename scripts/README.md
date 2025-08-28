
# Scripts

- `pack_m365.py` : แพ็กโฟลเดอร์ `appPackage/` ให้กลายเป็นไฟล์ .zip
  - ตัวอย่าง:
    ```bash
    python scripts/pack_m365.py --src m365/appPackage --out thanyaaura-m365-private.zip
    python scripts/pack_m365.py --src store/appPackage --out thanyaaura-m365-store.zip
    ```
- `pack.ps1` : เวอร์ชัน PowerShell สำหรับ Windows
