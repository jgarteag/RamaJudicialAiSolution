# RamaJudicialAiSolution

Plataforma de búsqueda de estados judiciales en Colombia con IA.

## 🏗️ Arquitectura por Microstacks

```
RamaJudicialAiSolution/
├── frontend/                          # Microstack 1: Chat interactivo
│   ├── index.html
│   ├── styles.css
│   ├── app.js                        # Lógica del chat (llama API real)
│   └── config.js                     # Endpoint API (generado por CD)
├── backend/                           # Microstack 2: Backend API
│   └── lambda/
│       └── handler.py                # Lambda Python 3.12
├── infrastructure/                    # IaC (Terraform modular)
│   ├── modules/
│   │   ├── s3-frontend/             # Bucket S3 privado + encrypted
│   │   ├── cloudfront/              # CDN + HTTPS + Security Headers
│   │   ├── api-gateway/             # HTTP API v2 (low cost)
│   │   └── lambda/                  # Lambda + IAM + CloudWatch
│   ├── main.tf                      # Orquestador de módulos
│   ├── providers.tf                 # AWS provider + S3 backend
│   ├── variables.tf
│   └── outputs.tf
├── deploy/                           # Scripts de despliegue local
│   ├── deploy-frontend.sh
│   └── redeploy.sh
└── .github/workflows/
    └── deploy.yml                   # Pipeline unificado CI→CD
```

## 🚀 Microstacks

| # | Stack | Estado | Descripción |
|---|-------|--------|-------------|
| 1 | Frontend + S3 + CloudFront | ✅ Completado | Chat UI, S3 privado, CloudFront con OAC |
| 2 | Backend API (Lambda + API GW) | ✅ Completado | HTTP API v2, Lambda Python, CORS |
| 3 | IA (Bedrock/LLM) | 🔜 Próximo | Integrar Bedrock para respuestas inteligentes |
| 4 | Data Layer | 🔜 Pendiente | Conexión a fuentes de datos judiciales |
| 5 | Auth & Rate Limiting | 🔜 Pendiente | Cognito o API keys |

## 🌐 URLs en Producción

| Recurso | URL |
|---------|-----|
| Frontend | https://d3fib2d1qj37tw.cloudfront.net |
| API | https://8q2bno5j47.execute-api.us-east-1.amazonaws.com |
| Health Check | https://8q2bno5j47.execute-api.us-east-1.amazonaws.com/api/health |

## 📡 API Endpoints

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/api/health` | Health check del servicio |
| POST | `/api/chat` | Enviar consulta judicial |

```bash
# Ejemplo de uso
curl -X POST https://8q2bno5j47.execute-api.us-east-1.amazonaws.com/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Quiero consultar el radicado 2023-00145"}'
```

## 🔄 Pipeline CI/CD (Unificado)

Un solo workflow `deploy.yml` con dos jobs:

```
┌─────────────────────────────────────────────────────┐
│  Trigger: push a trunk | PR | workflow_dispatch     │
├─────────────────────────────────────────────────────┤
│                                                     │
│  [Validate & Plan] ─── automático                   │
│       │                                             │
│       ▼                                             │
│  [⏸️ Approval] ─── review en environment            │
│       │             'production'                    │
│       ▼                                             │
│  [CD: Deploy] ─── terraform apply + frontend sync   │
│                                                     │
└─────────────────────────────────────────────────────┘
```

**Ejecución manual desde GitHub UI:**
1. Actions → Deploy Pipeline → Run workflow
2. Seleccionar branch + microstack: `all`, `frontend`, `backend-api`
3. CI corre automático → Aprobar deploy → CD ejecuta

**En PRs:** solo corre validación (fmt + validate + plan + comentario).

## 💰 Costos

| Servicio | Costo estimado | Free Tier |
|----------|---------------|-----------|
| CloudFront | ~$0/mes | 1 TB transfer/mes gratis |
| S3 | ~$0/mes | 5 GB gratis |
| Lambda | ~$0/mes | 1M requests/mes gratis |
| API Gateway HTTP | ~$0/mes | 1M requests/mes gratis |
| CloudWatch Logs | ~$0/mes | 5 GB ingestion gratis |
| **Total** | **~$0/mes** | **En desarrollo** |

> En producción con tráfico real: ~$1-5/mes para uso moderado.

## 📋 Requisitos

- Terraform >= 1.5
- AWS CLI v2 con SSO configurado
- Python 3.12 (para Lambda)
- GitHub repo con OIDC configurado

## 🛠️ Deploy Local

```bash
# 1. Autenticación AWS (SSO)
eval "$(aws configure export-credentials --profile admindev --format env)"

# 2. Infraestructura
cd infrastructure
terraform init
terraform plan
terraform apply

# 3. Frontend
cd ..
aws s3 sync frontend/ s3://$(cd infrastructure && terraform output -raw s3_bucket_id)/ --delete
```

## 🔐 Configuración GitHub

**Secretos:**
| Secreto | Descripción |
|---------|-------------|
| `AWS_ROLE_TO_ASSUME` | ARN del IAM Role OIDC (`GitHubActionsDeployRole`) |

**Variables:**
| Variable | Valor |
|----------|-------|
| `AWS_REGION` | `us-east-1` |

**Environments:**
| Environment | Configuración |
|-------------|--------------|
| `production` | Required reviewers (aprobación antes de deploy) |

## 🗺️ Roadmap - Próximos Pasos

### Microstack 3: IA con Bedrock
- [ ] Integrar Amazon Bedrock (Claude/Titan)
- [ ] Prompt engineering para consultas judiciales
- [ ] Contexto conversacional (historial de chat)
- [ ] Guardrails para respuestas apropiadas

### Microstack 4: Data Layer
- [ ] Conexión a fuentes de datos de la Rama Judicial
- [ ] Scraping/API de consulta de radicados
- [ ] Cache de resultados (DynamoDB/ElastiCache)

### Microstack 5: Auth & Seguridad
- [ ] Rate limiting por IP
- [ ] API keys o Cognito
- [ ] WAF en CloudFront

### Mejoras generales
- [ ] Custom domain (rama-judicial-ai.com)
- [ ] Monitoring y alertas (CloudWatch Alarms)
- [ ] Tests unitarios y de integración
- [ ] Ambientes separados (dev/staging/prod)
