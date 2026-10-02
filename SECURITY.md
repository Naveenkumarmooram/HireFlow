# Security

Report suspected vulnerabilities privately to the repository owner through GitHub private vulnerability reporting when enabled. Do not publish applicant data, credentials or private candidate/offer links in issues.

Never commit `.env`, database passwords, JWT secrets, encryption keys or Vercel credentials. Use separate secrets for staging and production, rotate exposed values, and preserve encryption-key recovery.

Review [deployment](docs/DEPLOYMENT.md), [operations](docs/OPERATIONS.md) and [release requirements](docs/RELEASE_CHECKLIST.md) before handling real applicant information. Passing automated checks is not evidence of regulatory certification.
