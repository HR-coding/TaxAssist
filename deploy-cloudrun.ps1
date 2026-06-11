# TaxAssist -> Google Cloud Run (single container: API + frontend)
# Run from the project root:
#   powershell -ExecutionPolicy Bypass -File .\deploy-cloudrun.ps1 -Project tax-agent-orchestrator

param(
  [Parameter(Mandatory=$true)][string]$Project,
  [string]$Region = "asia-south1",
  [string]$Service = "taxassist"
)

# Not using ErrorActionPreference=Stop on purpose: gcloud writes normal output to
# stderr, which PowerShell would otherwise treat as a fatal error.

gcloud config set project $Project | Out-Null
gcloud config set run/region $Region | Out-Null

Write-Host "== Enabling APIs ==" -ForegroundColor Cyan
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com

Write-Host "== Artifact Registry ==" -ForegroundColor Cyan
gcloud artifacts repositories create $Service --repository-format=docker --location=$Region 2>$null
Write-Host "  repo ready: $Service"

function Set-Secret($name, $value) {
  $exists = (gcloud secrets describe $name --format="value(name)" 2>$null)
  if ($exists) { $value | gcloud secrets versions add $name --data-file=- | Out-Null }
  else         { $value | gcloud secrets create  $name --data-file=- | Out-Null }
  Write-Host "  secret set: $name"
}
function Set-FileSecret($name, $file) {
  if (-not (Test-Path $file)) { Write-Host "  missing $file - skipping $name" -ForegroundColor Yellow; return }
  $exists = (gcloud secrets describe $name --format="value(name)" 2>$null)
  if ($exists) { gcloud secrets versions add $name --data-file=$file | Out-Null }
  else         { gcloud secrets create  $name --data-file=$file | Out-Null }
  Write-Host "  file secret set: $name ($file)"
}

Write-Host "== Loading secrets from .env ==" -ForegroundColor Cyan
$envMap = @{}
Get-Content .env | Where-Object { $_ -match "^\s*[A-Z]" } | ForEach-Object {
  $kv = $_ -split "=", 2
  $key = $kv[0].Trim()
  $val = ($kv[1] -split "#")[0].Trim()
  if ($val) { $envMap[$key] = $val }
}
foreach ($k in "MONGO_URI","GOOGLE_API_KEY","AGENT_SECRET_KEY","CONTROL_ENC_KEY","POLL_TOKEN","MONGODB_MCP_TOKEN","GOOGLE_OAUTH_CLIENT_ID","GOOGLE_OAUTH_CLIENT_SECRET") {
  if ($envMap[$k]) { Set-Secret $k $envMap[$k] }
}
Set-FileSecret "google-credentials" "credentials.json"
Set-FileSecret "google-token" "token.json"

Write-Host "== Granting Secret Manager access ==" -ForegroundColor Cyan
$projNum = (gcloud projects describe $Project --format="value(projectNumber)")
$runtimeSA = "$projNum-compute@developer.gserviceaccount.com"
gcloud projects add-iam-policy-binding $Project --member "serviceAccount:$runtimeSA" --role "roles/secretmanager.secretAccessor" | Out-Null
Write-Host "  granted to $runtimeSA"

Write-Host "== Building image (this takes a few minutes) ==" -ForegroundColor Cyan
$img = "$Region-docker.pkg.dev/$Project/$Service/app:latest"
gcloud builds submit --tag $img
if ($LASTEXITCODE -ne 0) { Write-Host "BUILD FAILED - see errors above." -ForegroundColor Red; exit 1 }

Write-Host "== Deploying to Cloud Run ==" -ForegroundColor Cyan
gcloud run deploy $Service --image $img --region $Region --allow-unauthenticated --min-instances 1 --max-instances 1 --memory 1Gi --set-env-vars "MONGODB_DB=tax_agent_db,ORCHESTRATOR_MODEL=gemini-2.0-flash,AGENT_REQUIRE_SIGNATURE=0,POSTGRES_URL=sqlite+pysqlite:////app/taxassist.db,GOOGLE_CREDENTIALS_FILE=/secrets/cred/credentials.json,GOOGLE_TOKEN_FILE=/secrets/tok/token.json" --set-secrets "MONGO_URI=MONGO_URI:latest,GOOGLE_API_KEY=GOOGLE_API_KEY:latest,AGENT_SECRET_KEY=AGENT_SECRET_KEY:latest,CONTROL_ENC_KEY=CONTROL_ENC_KEY:latest,POLL_TOKEN=POLL_TOKEN:latest,GOOGLE_OAUTH_CLIENT_ID=GOOGLE_OAUTH_CLIENT_ID:latest,GOOGLE_OAUTH_CLIENT_SECRET=GOOGLE_OAUTH_CLIENT_SECRET:latest,/secrets/cred/credentials.json=google-credentials:latest,/secrets/tok/token.json=google-token:latest"

if ($LASTEXITCODE -eq 0) {
  Write-Host ""
  Write-Host "DONE. Your app URL is shown above (https://$Service-...run.app)." -ForegroundColor Green
  Write-Host "Next: add  <thatURL>/auth/google/callback  to your Web OAuth client redirect URIs." -ForegroundColor Green
} else {
  Write-Host "Deploy failed - paste the error above." -ForegroundColor Red
}
