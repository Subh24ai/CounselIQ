"""Seed a small set of REAL regulatory updates for the Regulatory Monitor.

Run manually (not via Celery)::

    python -m scripts.seed_regulatory_updates

IMPORTANT — accuracy & verification
-----------------------------------
The summaries below describe genuine, well-known Indian regulatory instruments
and are written as *accurate general descriptions*. They deliberately avoid
quoting specific circular/notification numbers or precise gazette dates, because
those specifics must be confirmed against the official source before this data
is shown to a real client.

``published_date`` values marked ``# VERIFIED`` correspond to widely-reported
enactment/publication dates. Values marked ``# ILLUSTRATIVE`` are approximate
placeholders for instruments that are issued/updated on a rolling basis — the
compliance team MUST replace these (and add the exact circular number to the
title) before relying on them operationally.

URLs point only to the regulator's stable top-level domain, not to a specific
document, to avoid linking to a page that may have moved.
"""

from __future__ import annotations

import asyncio
from datetime import date

from app.db.session import async_session_factory
from app.schemas.regulatory import RegulatoryUpdateCreate
from app.services.regulatory import create_regulatory_update

# Each entry: a real instrument, accurately summarised in general terms.
SEED_UPDATES: list[RegulatoryUpdateCreate] = [
    RegulatoryUpdateCreate(
        source="other",
        title="Digital Personal Data Protection Act, 2023 — core obligations",
        summary=(
            "India's first comprehensive data-protection statute. It governs the "
            "processing of digital personal data, requires a lawful basis "
            "(primarily consent) for processing, mandates clear notice to data "
            "principals, grants rights such as access, correction and erasure, and "
            "imposes obligations on data fiduciaries including purpose limitation, "
            "data-breach notification and security safeguards. Contracts involving "
            "personal data sharing, processing or cross-border transfer should be "
            "reviewed for consent, data-processing-agreement and breach-notice "
            "clauses."
        ),
        full_text=None,
        url="https://www.meity.gov.in",
        # VERIFIED — received Presidential assent 11 Aug 2023.
        published_date=date(2023, 8, 11),
    ),
    RegulatoryUpdateCreate(
        source="SEBI",
        title="SEBI (LODR) Regulations — listed-entity disclosure obligations",
        summary=(
            "The SEBI (Listing Obligations and Disclosure Requirements) "
            "Regulations set out continuous-disclosure, corporate-governance and "
            "related-party-transaction obligations for listed entities, including "
            "board composition, audit-committee approval of material related-party "
            "transactions, and timely disclosure of material events. Vendor, "
            "services and intra-group agreements with listed entities should be "
            "checked for related-party-transaction approval and disclosure "
            "triggers."
        ),
        full_text=None,
        url="https://www.sebi.gov.in",
        # VERIFIED — original LODR notification 2 Sep 2015. Amended many times
        # since; verify the latest amendment before client use.
        published_date=date(2015, 9, 2),
    ),
    RegulatoryUpdateCreate(
        source="IRDAI",
        title="IRDAI guidelines on insurance distribution and commission disclosure",
        summary=(
            "IRDAI regulates the distribution of insurance products, including "
            "expenses of management and commission/remuneration payable to "
            "intermediaries, and requires transparency in distribution "
            "arrangements. Distribution, corporate-agency and bancassurance "
            "agreements should be reviewed for commission caps, disclosure and "
            "conflict-of-interest provisions consistent with the prevailing IRDAI "
            "framework."
        ),
        full_text=None,
        url="https://irdai.gov.in",
        # ILLUSTRATIVE — IRDAI updates these on a rolling basis; verify the
        # exact regulation and date.
        published_date=date(2023, 3, 26),
    ),
    RegulatoryUpdateCreate(
        source="RBI",
        title="RBI Master Direction on outsourcing of IT services by regulated entities",
        summary=(
            "RBI's framework on outsourcing of information-technology services "
            "requires regulated entities (banks, NBFCs and similar) to retain "
            "accountability for outsourced activities, conduct due diligence on "
            "service providers, and include specific safeguards in outsourcing "
            "contracts — covering audit and inspection rights, data "
            "confidentiality and security, business continuity, sub-contracting "
            "controls, and exit/termination. IT and cloud-services agreements with "
            "regulated entities should be checked against these requirements."
        ),
        full_text=None,
        url="https://www.rbi.org.in",
        # VERIFIED — RBI Master Direction on Outsourcing of IT Services issued
        # April 2023.
        published_date=date(2023, 4, 10),
    ),
    RegulatoryUpdateCreate(
        source="MCA",
        title="Companies Act, 2013 — related-party transactions (Section 188)",
        summary=(
            "Section 188 of the Companies Act, 2013 governs related-party "
            "transactions, requiring board (and, above prescribed thresholds, "
            "shareholder) approval for specified transactions such as sale or "
            "purchase of goods/services, property and appointment to office of "
            "profit, along with disclosure in the board's report. Intercompany and "
            "affiliate contracts should be reviewed for related-party "
            "identification, approval thresholds and disclosure obligations."
        ),
        full_text=None,
        url="https://www.mca.gov.in",
        # VERIFIED — Companies Act, 2013 received assent 29 Aug 2013; published
        # shortly after.
        published_date=date(2013, 8, 30),
    ),
    RegulatoryUpdateCreate(
        source="RBI",
        title="RBI Master Direction on Know Your Customer (KYC)",
        summary=(
            "RBI's KYC Master Direction prescribes customer-identification, "
            "due-diligence and record-keeping requirements for regulated entities "
            "to prevent money laundering and terrorist financing, including "
            "customer acceptance policy, risk categorisation and periodic "
            "updation. Onboarding, agency and payment-processing agreements should "
            "reflect KYC/AML obligations and audit rights."
        ),
        full_text=None,
        url="https://www.rbi.org.in",
        # VERIFIED — KYC Master Direction first issued Feb 2016; amended
        # periodically, so verify the latest version.
        published_date=date(2016, 2, 25),
    ),
    RegulatoryUpdateCreate(
        source="SEBI",
        title="SEBI (Prohibition of Insider Trading) Regulations, 2015",
        summary=(
            "The PIT Regulations prohibit trading in securities while in "
            "possession of unpublished price-sensitive information (UPSI) and "
            "require listed entities and intermediaries to maintain a code of "
            "conduct, structured digital database of UPSI, and controls over "
            "sharing of UPSI with third parties. Confidentiality and "
            "information-sharing clauses in agreements with listed entities should "
            "account for UPSI handling."
        ),
        full_text=None,
        url="https://www.sebi.gov.in",
        # VERIFIED — PIT Regulations notified Jan 2015; amended since, so verify
        # the latest amendment.
        published_date=date(2015, 1, 15),
    ),
    RegulatoryUpdateCreate(
        source="NABH",
        title="NABH accreditation standards for hospitals — patient data and consent",
        summary=(
            "NABH (National Accreditation Board for Hospitals & Healthcare "
            "Providers) accreditation standards include requirements around "
            "patient rights, informed consent, and confidentiality/security of "
            "patient health information. Hospital service, technology and "
            "data-processing contracts should be reviewed for consent, "
            "confidentiality and data-security obligations consistent with NABH "
            "standards and applicable data-protection law."
        ),
        full_text=None,
        url="https://nabh.co",
        # ILLUSTRATIVE — NABH standards are revised in editions; verify the
        # current edition and its date.
        published_date=date(2020, 1, 1),
    ),
]


async def _seed() -> None:
    async with async_session_factory() as session:
        created = 0
        for data in SEED_UPDATES:
            record = await create_regulatory_update(session, data)
            created += 1
            print(f"  ✓ [{record.source}] {record.title}  (id={record.id})")
        print(f"\nSeeded {created} regulatory update(s).")
        print(
            "NOTE: published dates marked ILLUSTRATIVE and circular numbers are "
            "placeholders — verify against the official source before client use."
        )


if __name__ == "__main__":
    print("Seeding regulatory updates (generating embeddings locally)…\n")
    asyncio.run(_seed())
