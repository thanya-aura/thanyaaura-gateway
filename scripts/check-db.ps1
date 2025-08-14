# scripts/check-db.ps1 — quick Postgres sanity checks (non-interactive)
# Uses embedded password as requested.
$PSQL   = "C:\Program Files\PostgreSQL\17\bin\psql.exe"

# === EDITABLE ===
$DBPARMS = "host=dpg-d2e1kvbuibrs738im6s0-a.singapore-postgres.render.com port=5432 dbname=thanyaaura_entitlement user=thanyaaura_admin password='YdIb7eiPjpYS5VcYfEltdEA2hIrME3mC' sslmode=require"
$EMAIL   = "buyer@example.com"

Write-Host "Checking database connection..." -ForegroundColor Cyan
& "$PSQL" "$DBPARMS" -c "SELECT 1;"
& "$PSQL" "$DBPARMS" -c "SELECT current_database(), current_user;"

Write-Host "`nEnsuring products table has 36 SKUs..." -ForegroundColor Cyan
& "$PSQL" "$DBPARMS" -c @"
INSERT INTO products (sku) VALUES
('cfs'),('cfp'),('cfpr'),
('revs'),('revp'),('revpr'),
('capexs'),('capexp'),('capexpr'),
('fxs'),('fxp'),('fxpr'),
('costs'),('costp'),('costpr'),
('buds'),('budp'),('budpr'),
('reps'),('repp'),('reppr'),
('vars'),('varp'),('varpr'),
('mars'),('marp'),('marpr'),
('fors'),('forp'),('forpr'),
('decs'),('decp'),('decpr'),
('standard'),('plus'),('premium')
ON CONFLICT (sku) DO NOTHING;
"@

Write-Host "`nRecent subscriptions..." -ForegroundColor Cyan
& "$PSQL" "$DBPARMS" -c "SELECT id, user_email, sku, status FROM subscriptions ORDER BY created_at DESC LIMIT 10;"

Write-Host "`nEffective agents for $EMAIL ..." -ForegroundColor Cyan
& "$PSQL" "$DBPARMS" -P "pager=off" -c "SELECT count(*) AS total FROM effective_agents('$EMAIL');"
& "$PSQL" "$DBPARMS" -P "pager=off" -c "SELECT * FROM effective_agents('$EMAIL') ORDER BY agent_slug;"
