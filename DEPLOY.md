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

The Azure CLI and the Container Apps extension are required. Run this from the
repository root:

```bash
az login
az extension add --name containerapp --upgrade

export AZURE_LOCATION=swedencentral
export AZURE_RESOURCE_GROUP=raja-demo
export RAJA_APP_NAME=raja-gateway
export RAJA_SERVER_KEY="$(openssl rand -hex 32)"
export RAJA_DEMO_SECRET="$(openssl rand -hex 32)"

az group create \
  --name "$AZURE_RESOURCE_GROUP" \
  --location "$AZURE_LOCATION"

az containerapp up \
  --name "$RAJA_APP_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --location "$AZURE_LOCATION" \
  --source . \
  --ingress external \
  --target-port 8000 \
  --min-replicas 1 \
  --max-replicas 1
```

`az containerapp up --source .` builds the included `Dockerfile`. Add the
secrets immediately, then bind them to the container:

```bash
az containerapp secret set \
  --name "$RAJA_APP_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --secrets \
    raja-server-key="$RAJA_SERVER_KEY" \
    raja-demo-secret="$RAJA_DEMO_SECRET"

az containerapp update \
  --name "$RAJA_APP_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --set-env-vars \
    RAJA_SERVER_KEY=secretref:raja-server-key \
    RAJA_DEMO_SECRET=secretref:raja-demo-secret
```

After Azure returns the FQDN, update the app with the public URL used by
approval links:

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

For a real deployment, create the two Container Apps secrets in the Azure
portal or with `az containerapp secret set`, then reference them from the
environment variables. Do not enable `RAJA_DEMO_MODE`; production startup
must fail closed unless explicit secrets are present.

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
