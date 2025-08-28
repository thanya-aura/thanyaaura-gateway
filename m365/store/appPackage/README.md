
# Thanyaaura Finance Agent (Store) – App Package

- ใช้สำหรับการส่งขึ้น Microsoft AppSource / Agents Store
- แก้ไขค่า:
  - `manifest.json` → `id` (GUID เฉพาะชุด store), ข้อมูล publisher/website/privacy/terms
  - `thanyaaura-plugin.json` → ตั้งค่า `OAuthPluginVault.reference_id` สำหรับ production
  - ปรับคำอธิบาย/พรอมป์ทให้ตรงกับรายการในสโตร์ (รองรับทั้งไทย/อังกฤษ)

การแพ็กไฟล์เพื่อส่ง:
- zip ทั้งโฟลเดอร์ `appPackage/` ให้เป็นไฟล์เดียว (ตัวอย่างสคริปต์ดูในแพ็กเกจ scripts)
