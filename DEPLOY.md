# Deploying Raja

The supported deployment target is **Azure Container Apps**. This gives the
project a public HTTPS MCP endpoint and approval URL while keeping the
gateway as one process, which matches the current SQLite state model.

## Build and run locally

```bash
docker build -t raja-gateway .
docker run --rm -p 8000:8000 \
  -e RAJA_SERVER_KEY="$(openssl rand -hex 32)" \
  -e RAJA_DEMO_SECRET="$(openssl rand -hex 32)" \
  -e RAJA_PUBLIC_BASE_URL=http://127.0.0.1:8000 \
  raja-gateway
```

Check `http://127.0.0.1:8000/healthz` and the MCP endpoint at
`http://127.0.0.1:8000/mcp`.

## Azure Container Apps quickstart

Live deployment: https://raja-gateway.proudsea-6cbc91b7.swedencentral.azurecontainerapps.io
(resource group `raja-demo`, registry `caf99923d346acr`).

Requirements: Azure CLI with the Container Apps extension, and Docker with
`buildx` (on macOS with Colima: `brew install docker-buildx` and symlink it
into `~/.docker/cli-plugins/`). The image is built locally for `linux/amd64`
and pushed; `az containerapp up --source .` is not usable here because ACR
Tasks are disabled on this subscription (`TasksOperationsNotAllowed`) and the
CLI's source tarball also chokes on git's fsmonitor socket in `.git/`.

```bash
az login
az extension add --name containerapp --upgrade
az provider register -n Microsoft.App --wait
az provider register -n Microsoft.ContainerRegistry --wait
az provider register -n Microsoft.OperationalInsights --wait

export AZURE_LOCATION=swedencentral
export AZURE_RESOURCE_GROUP=raja-demo
export RAJA_APP_NAME=raja-gateway
export ACR_NAME=caf99923d346acr
export RAJA_SERVER_KEY="$(openssl rand -hex 32)"
export RAJA_DEMO_SECRET="$(openssl rand -hex 32)"

az group create --name "$AZURE_RESOURCE_GROUP" --location "$AZURE_LOCATION"
az acr create --name "$ACR_NAME" --resource-group "$AZURE_RESOURCE_GROUP" --sku Basic
az containerapp env create \
  --name "$RAJA_APP_NAME-env" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --location "$AZURE_LOCATION"
```

Build, push, and create the app (secrets are bound at creation, so the
container never starts without them):

```bash
az acr login --name "$ACR_NAME"
docker buildx build --platform linux/amd64 \
  -t "$ACR_NAME.azurecr.io/raja-gateway:v1" --load .
docker push "$ACR_NAME.azurecr.io/raja-gateway:v1"

az containerapp create \
  --name "$RAJA_APP_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --environment "$RAJA_APP_NAME-env" \
  --image "$ACR_NAME.azurecr.io/raja-gateway:v1" \
  --registry-server "$ACR_NAME.azurecr.io" \
  --registry-identity system \
  --ingress external \
  --target-port 8000 \
  --min-replicas 1 \
  --max-replicas 1 \
  --secrets raja-server-key="$RAJA_SERVER_KEY" raja-demo-secret="$RAJA_DEMO_SECRET" \
  --env-vars RAJA_SERVER_KEY=secretref:raja-server-key RAJA_DEMO_SECRET=secretref:raja-demo-secret
```

After Azure returns the FQDN, set the public URL. It is used for approval
links and is also the host the MCP transport's DNS-rebinding protection
allows, so `/mcp` answers `Invalid Host header` until this is set:

```bash
export RAJA_PUBLIC_BASE_URL="https://$(az containerapp show \
  --name "$RAJA_APP_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --query properties.configuration.ingress.fqdn -o tsv)"

az containerapp update \
  --name "$RAJA_APP_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --set-env-vars "RAJA_PUBLIC_BASE_URL=$RAJA_PUBLIC_BASE_URL"
```

To ship a code change, bump the tag, build and push again, then
`az containerapp update ... --image "$ACR_NAME.azurecr.io/raja-gateway:v2"`.

Verify with `curl "$RAJA_PUBLIC_BASE_URL/healthz"` and run the wire-level demo
against it (needs the same `RAJA_DEMO_SECRET` exported locally):

```bash
RAJA_GATEWAY_URL="$RAJA_PUBLIC_BASE_URL" uv run python -m demo.local_fallback
```

Do not enable `RAJA_DEMO_MODE` in the deployment; startup must fail closed
unless explicit secrets are present.

## Important prototype boundary

The current state layer is SQLite and is intentionally configured for one
replica and one writer. Keep `min-replicas=1` and `max-replicas=1` for a
hackathon deployment. Container restarts preserve state only if `/app/data` is
mounted to persistent Azure storage; otherwise the app remains functional but
loses local ledger and approval state on replacement. A production deployment
should move state and replay protection to a server-backed database before
scaling horizontally.

The Streamlit console can be run locally against the deployed gateway by
setting `RAJA_GATEWAY_URL` to the Container App URL, or deployed as a second
Container App using the existing `streamlit run console/app.py` command.
