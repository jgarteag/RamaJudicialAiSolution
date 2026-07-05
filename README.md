# RamaJudicialAiSolution
Busqueda de estados judiciales Colombia

## Git flow recomendado (trunk-based)

- Ramas de trabajo: `feature/*`
- Integracion: Pull Request hacia `trunk`
- CI: se ejecuta en cada PR hacia `trunk`
- CD: se ejecuta al hacer merge/push en `trunk`

## GitHub Actions

Este repositorio incluye:

- `.github/workflows/ci.yml`: validacion base para PRs a `trunk`
- `.github/workflows/cd.yml`: despliegue base a AWS en push a `trunk`

### Secretos requeridos para CD

- `AWS_ROLE_TO_ASSUME`: IAM Role para OIDC desde GitHub Actions

### Variables recomendadas

- `AWS_REGION` (GitHub Variables), ejemplo: `us-east-1`
