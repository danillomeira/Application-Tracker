# data/ (fora do git)

Dados pessoais de quem usa o app. Tudo nesta pasta, exceto este README, está no `.gitignore`.

| Caminho | Conteúdo |
|---|---|
| `storage/` | PDFs gerados, importações e anexos (backend de storage `local`) |
| `master-profile.yaml` | Opcional: currículo mestre em YAML, para quem prefere arquivo ao onboarding. Importe com `cd backend && uv run tracker-seed` |
| `cvs/` | Opcional: seus `.tex` próprios no estilo `classic` |

O caminho normal é o onboarding do dashboard: você envia o PDF do LinkedIn ou o CV e confirma o que a IA extraiu.
