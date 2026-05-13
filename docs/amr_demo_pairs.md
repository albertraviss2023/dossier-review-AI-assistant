# AMR Demo Pairs (Pass vs Query)

Use these pairs for a clear side-by-side AMR stewardship demonstration.

## Dataset
- Root: `synthetic_dossier_dataset_scans_challenge_24`
- Manifest: `synthetic_dossier_dataset_scans_challenge_24/manifests/dossier_manifests.jsonl`

## Pair A: Human Antimicrobial (Reserve)
- Family: `FAM-0001`
- Pass dossier: `HUM-NEW-INNOV-AMR-SYNT-0001`
- Query dossier: `HUM-NEW-INNOV-AMR-SYNT-0001-Q`
- Category: `human / new_submission / innovator / antimicrobial / Reserve`

PDFs
- `synthetic_dossier_dataset_scans_challenge_24/rendered_pdfs/human/new_submissions/HUM-NEW-INNOV-AMR-SYNT-0001.pdf`
- `synthetic_dossier_dataset_scans_challenge_24/rendered_pdfs/human/new_submissions/HUM-NEW-INNOV-AMR-SYNT-0001-Q.pdf`

## Pair B: Veterinary Antimicrobial (Watch)
- Family: `FAM-0002`
- Pass dossier: `VET-NEW-BIO-AMR-OXYT-0003`
- Query dossier: `VET-NEW-BIO-AMR-OXYT-0003-Q`
- Category: `veterinary / new_submission / biosimilar_or_biological / antimicrobial / Watch`

PDFs
- `synthetic_dossier_dataset_scans_challenge_24/rendered_pdfs/veterinary/new_submissions/VET-NEW-BIO-AMR-OXYT-0003.pdf`
- `synthetic_dossier_dataset_scans_challenge_24/rendered_pdfs/veterinary/new_submissions/VET-NEW-BIO-AMR-OXYT-0003-Q.pdf`

## Suggested Demo Prompts
1. `Perform data quality and vision extraction check for this dossier.`
2. `Review AMR stewardship implications and provide authorization control.`
3. `Run the Veterinary AMR + Food Safety check and explain withdrawal/residue decision impact.`
4. `Provide final recommendation with evidence-grounded findings.`

## Expected Demo Story
- Pass dossier: AMR controls present and decision remains acceptable under stewardship policy.
- Query dossier: missing or incomplete AMR controls trigger `query_applicant`.
- Veterinary query should clearly flag withdrawal/residue and food-safety AMR warning issues.
