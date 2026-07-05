# RamaJudicialAiSolution

Plataforma de búsqueda de estados judiciales en Colombia con IA.

## 🏗️ Arquitectura por Microstacks

```
RamaJudicialAiSolution/
├── frontend/                          # Microstack 1: Chat interactivo con IA
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── infrastructure/                    # IaC (Terraform modular)
│   ├── modules/
│   │   ├── s3-frontend/              # Bucket S3 privado
│   │   └── cloudfront/              # CDN + HTTPS + Security Headers
│   ├── main.tf                       # Orquestador
│   ├── providers.tf
│   ├── variables.tf
│   ├── outputs.tf
│   └── terraform.tfvars.example
├── deploy/                           # Scripts de despliegue
│   ├── deploy-frontend.sh           # S3 sync + CF invalidation
│   └── redeploy.sh                  # Orquestador de deploys
└── .github/workflows/                # CI/CD
    ├── ci.yml                       # Validación en PRs
    └── cd.yml                       # Deploy en merge a trunk
```

## 🚀 Microstacks

| # | Stack | Estado | Descripción |
|---|-------|--------|-------------|
| 1 | Frontend + S3 + CloudFront | ✅ Listo | Chat interactivo, hosting estático |
| 2 | Backend API (Lambda + API GW) | 🔜 Próximo | API REST para consultas IA |
| 3 | IA (Bedrock/LLM) | 🔜 Pendiente | Procesamiento inteligente de consultas |
| 4 | Data Layer (MongoDB) | 🔜 Pendiente | Conexión a base de datos de radicados |

## 📋 Requisitos

- Terraform >= 1.5
- AWS CLI v2
- Cuenta AWS con OIDC configurado para GitHub Actions

## 🛠️ Deploy local

```bash
# 1. Configurar variables
cd infrastructure
cp terraform.tfvars.example terraform.tfvars
# Editar terraform.tfvars con tu perfil AWS

# 2. Desplegar infraestructura
terraform init
terraform plan
terraform apply

# 3. Subir frontend
cd ..
./deploy/deploy-frontend.sh
```

## 🔄 Git Flow (Trunk-based)

- Ramas de trabajo: `feature/*`
- Integración: Pull Request hacia `trunk`
- **CI**: terraform fmt + validate + tests (en cada PR)
- **CD**: terraform apply + deploy frontend (push a `trunk`)

## 🔐 Secretos requeridos (GitHub)

| Secreto | Descripción |
|---------|-------------|
| `AWS_ROLE_TO_ASSUME` | ARN del IAM Role para OIDC |

## 📦 Variables de GitHub

| Variable | Ejemplo |
|----------|---------|
| `AWS_REGION` | `us-east-1` |
