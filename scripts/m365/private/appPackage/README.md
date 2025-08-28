
# Thanyaaura Finance Agent (Private) – App Package

- ใช้สำหรับขายตรง/ติดตั้งนอกสโตร์ (ผ่าน ThriveCart + sideload/atk)
- แก้ไขค่าต่อไปนี้ก่อนใช้งานจริง:
  - `manifest.json` → `id` (GUID ถาวร), URLs ผู้พัฒนา
  - `thanyaaura-plugin.json` → ตั้งค่า `OAuthPluginVault.reference_id`
  - ตรวจสอบ `spec.url` ให้ชี้ไฟล์ OpenAPI จริง (`/openapi.json`)

ทดสอบติดตั้ง:
```
atk install --file-path thanyaaura-m365-private.zip
```
