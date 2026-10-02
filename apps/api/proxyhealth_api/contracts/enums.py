"""Every enum of the public API contract (API_CONTRACT §1).

All enums are ``str`` enums except ``PackTier`` (``IntEnum``). Values are the exact wire
strings; never rename them without bumping the contract version.
"""

from enum import IntEnum, StrEnum


class DataUseTier(StrEnum):
    """API_CONTRACT §1 — data-use tier the server runs on (mirrors ``X-Data-Use-Tier``).

    ``paid``/``unpaid``/``mixed``/``none`` come from the Gemini slot billing flags (D-01),
    ``demo`` from the mock. ``local`` (an open-weight model on a loopback endpoint of the API host)
    and ``attested`` (a hosted vendor whose API terms the operator attests say "no training";
    development only) exist only with ``AI_PROVIDER=openai_compat`` (free-ai-providers §5.2).
    """

    paid = "paid"
    unpaid = "unpaid"
    mixed = "mixed"
    demo = "demo"
    none = "none"
    local = "local"
    attested = "attested"


class Provider(StrEnum):
    """API_CONTRACT §1 — AI provider backing the server."""

    gemini = "gemini"
    mock = "mock"
    openai_compat = "openai_compat"


class ModelTier(StrEnum):
    """API_CONTRACT §1 — model tier a request is routed to."""

    pro = "pro"
    fast = "fast"


class ThinkingLevel(StrEnum):
    """API_CONTRACT §1 — Gemini thinking level used for a call."""

    minimal = "minimal"
    low = "low"
    medium = "medium"
    high = "high"


class ModelQuality(StrEnum):
    """API_CONTRACT §1 — ``degraded`` when the fast model served a pro task."""

    full = "full"
    degraded = "degraded"


class AnalysisMode(StrEnum):
    """API_CONTRACT §1 — how the analysis pipeline produced the result."""

    single = "single"
    two_call = "two_call"
    mock = "mock"


class DocumentCategory(StrEnum):
    """API_CONTRACT §1 — domain; drives disclaimers and resource routing."""

    immigration = "immigration"
    court = "court"
    medical = "medical"
    benefits = "benefits"
    housing = "housing"
    school = "school"
    employment = "employment"
    tax = "tax"
    civic = "civic"
    other = "other"


class DocumentType(StrEnum):
    """API_CONTRACT §1 — fine document taxonomy (see DOCUMENT_TAXONOMY.md)."""

    uscis_receipt = "uscis_receipt"
    uscis_rfe = "uscis_rfe"
    uscis_noid = "uscis_noid"
    uscis_biometrics = "uscis_biometrics"
    uscis_interview = "uscis_interview"
    uscis_approval = "uscis_approval"
    uscis_denial = "uscis_denial"
    nta = "nta"
    hearing_notice = "hearing_notice"
    ij_decision = "ij_decision"
    bia_notice = "bia_notice"
    ice_checkin = "ice_checkin"
    ead_related = "ead_related"
    green_card_related = "green_card_related"
    tps_related = "tps_related"
    asylum_fee_notice = "asylum_fee_notice"
    parole_related = "parole_related"
    medical_bill = "medical_bill"
    eob = "eob"
    insurance_denial = "insurance_denial"
    prior_auth = "prior_auth"
    lab_result = "lab_result"
    prescription_label = "prescription_label"
    discharge_instructions = "discharge_instructions"
    vaccine_record = "vaccine_record"
    appointment_reminder = "appointment_reminder"
    medicaid_renewal = "medicaid_renewal"
    snap_notice = "snap_notice"
    wic_notice = "wic_notice"
    ssa_letter = "ssa_letter"
    pay_or_quit = "pay_or_quit"
    eviction_summons = "eviction_summons"
    lease = "lease"
    rent_increase = "rent_increase"
    section8_recert = "section8_recert"
    utility_shutoff = "utility_shutoff"
    school_enrollment = "school_enrollment"
    immunization_notice = "immunization_notice"
    iep_504_notice = "iep_504_notice"
    school_meals = "school_meals"
    report_card = "report_card"
    w2_1099 = "w2_1099"
    i9 = "i9"
    offer_letter = "offer_letter"
    pay_stub = "pay_stub"
    irs_notice = "irs_notice"
    itin = "itin"
    jury_summons = "jury_summons"
    traffic_court = "traffic_court"
    other_notice = "other_notice"
    unknown = "unknown"


class SenderKind(StrEnum):
    """API_CONTRACT §1 — kind of organisation that sent the paper."""

    federal_agency = "federal_agency"
    state_agency = "state_agency"
    local_agency = "local_agency"
    court = "court"
    hospital_or_clinic = "hospital_or_clinic"
    insurer = "insurer"
    pharmacy = "pharmacy"
    landlord = "landlord"
    school = "school"
    employer = "employer"
    utility = "utility"
    bank_or_collector = "bank_or_collector"
    unknown = "unknown"


class Legibility(StrEnum):
    """API_CONTRACT §1 — how readable the captured pages were."""

    good = "good"
    partial = "partial"
    poor = "poor"


class UrgencyLevel(StrEnum):
    """API_CONTRACT §1 — code-computed urgency level (D-12)."""

    emergency = "emergency"
    critical = "critical"
    high = "high"
    medium = "medium"
    info = "info"


class Confidence(StrEnum):
    """API_CONTRACT §1 — three-step confidence scale."""

    high = "high"
    medium = "medium"
    low = "low"


class DemandKind(StrEnum):
    """API_CONTRACT §1 — what a demand item asks of the reader."""

    deadline = "deadline"
    relative_deadline = "relative_deadline"
    amount = "amount"
    document_requested = "document_requested"
    appointment = "appointment"
    action = "action"
    contact = "contact"


class DateKind(StrEnum):
    """API_CONTRACT §1 — whether a date was printed, computed, or left unresolved."""

    stated = "stated"
    estimated = "estimated"
    unresolved = "unresolved"


class RuleVerification(StrEnum):
    """API_CONTRACT §1 — provenance of a deadline rule."""

    verified = "verified"
    likely = "likely"


class PlanStepKind(StrEnum):
    """API_CONTRACT §1 — action verb of a plan step."""

    call = "call"
    mail = "mail"
    bring = "bring"
    gather = "gather"
    ask = "ask"
    visit = "visit"
    submit_online = "submit_online"
    wait = "wait"
    professional = "professional"
    verify = "verify"


class RedFlagKind(StrEnum):
    """API_CONTRACT §1 — kinds of red flags (model-found or code-found)."""

    scam_payment_method = "scam_payment_method"
    urgency_pressure = "urgency_pressure"
    impersonation = "impersonation"
    notario = "notario"
    fee_for_free_form = "fee_for_free_form"
    guaranteed_result = "guaranteed_result"
    unusual_contact = "unusual_contact"
    missing_pages = "missing_pages"
    contradiction = "contradiction"
    expired_date = "expired_date"
    jury_citizenship_warning = "jury_citizenship_warning"
    ead_receipt_not_work_authorization = "ead_receipt_not_work_authorization"
    not_a_court_order = "not_a_court_order"
    court_date_is_the_deadline = "court_date_is_the_deadline"
    no_fee_waiver = "no_fee_waiver"
    address_change_multi_agency = "address_change_multi_agency"
    injection_suspected = "injection_suspected"
    other = "other"


class Severity(StrEnum):
    """API_CONTRACT §1 — red-flag severity."""

    low = "low"
    medium = "medium"
    high = "high"


class ScamRisk(StrEnum):
    """API_CONTRACT §1 — code-scored scam risk (D-13)."""

    none = "none"
    possible = "possible"
    likely = "likely"


class DisclaimerKind(StrEnum):
    """API_CONTRACT §1 — disclaimers shown with a result."""

    legal_information_only = "legal_information_only"
    medical_information_only = "medical_information_only"
    benefits_information_only = "benefits_information_only"
    housing_information_only = "housing_information_only"
    general_information = "general_information"
    machine_translation = "machine_translation"
    verify_with_sender = "verify_with_sender"
    ai_generated = "ai_generated"
    degraded_model = "degraded_model"
    unpaid_tier_warning = "unpaid_tier_warning"
    demo_sample = "demo_sample"


class WarningCode(StrEnum):
    """API_CONTRACT §1 — machine-readable warnings attached to a result."""

    low_quality_image = "low_quality_image"
    partial_pages = "partial_pages"
    page_edge_crop = "page_edge_crop"
    degraded_model = "degraded_model"
    translation_partial = "translation_partial"
    blocked_partial = "blocked_partial"
    unpaid_tier = "unpaid_tier"
    demo_sample = "demo_sample"
    phrasing_lint_unavailable = "phrasing_lint_unavailable"
    emergency_lexicon_unavailable = "emergency_lexicon_unavailable"
    injection_masked = "injection_masked"
    contacts_stripped = "contacts_stripped"
    document_language_differs = "document_language_differs"


class RefusalKind(StrEnum):
    """API_CONTRACT §1 — why a chat answer was (partly) refused."""

    none = "none"
    eligibility = "eligibility"
    filing_advice = "filing_advice"
    outcome = "outcome"
    medical_interpretation = "medical_interpretation"
    drafting = "drafting"
    contact_request = "contact_request"
    out_of_scope = "out_of_scope"


class ReferTo(StrEnum):
    """API_CONTRACT §1 — who the user is referred to instead of the model."""

    none = "none"
    lawyer_or_accredited_rep = "lawyer_or_accredited_rep"
    clinician = "clinician"
    housing_counselor = "housing_counselor"
    benefits_office = "benefits_office"
    sender = "sender"


class TroubleshootMode(StrEnum):
    """API_CONTRACT §1 — what the troubleshoot endpoint is asked to do."""

    portal = "portal"
    scam_check = "scam_check"


class PortalHint(StrEnum):
    """API_CONTRACT §1 — kind of website/app shown in a troubleshoot screenshot."""

    benefits_portal = "benefits_portal"
    uscis_account = "uscis_account"
    eoir_portal = "eoir_portal"
    school_portal = "school_portal"
    hospital_portal = "hospital_portal"
    insurer_portal = "insurer_portal"
    irs_portal = "irs_portal"
    bank = "bank"
    other = "other"


class Tone(StrEnum):
    """API_CONTRACT §1 — explanation tone preference."""

    plain = "plain"
    formal = "formal"


class DateFormat(StrEnum):
    """API_CONTRACT §1 — how dates are rendered for the user."""

    auto = "auto"
    mdy = "mdy"
    dmy = "dmy"


class Direction(StrEnum):
    """API_CONTRACT §1 — script direction of a language."""

    ltr = "ltr"
    rtl = "rtl"


class DigitSystem(StrEnum):
    """API_CONTRACT §1 — digit system used when rendering numbers."""

    western = "western"
    eastern_arabic = "eastern_arabic"
    persian = "persian"
    devanagari = "devanagari"
    bengali = "bengali"
    gurmukhi = "gurmukhi"
    myanmar = "myanmar"
    ethiopic = "ethiopic"
    other = "other"


class PackTier(IntEnum):
    """API_CONTRACT §1 — language-pack support tier (the only ``IntEnum`` of the contract)."""

    tier_1 = 1
    tier_2 = 2
    tier_3 = 3


class PackSource(StrEnum):
    """API_CONTRACT §1 — where a language pack came from."""

    bundled = "bundled"
    generated = "generated"
    cache = "cache"


class ResourceTag(StrEnum):
    """API_CONTRACT §1 — closed vocabulary shared by prompts, resource DB and matcher."""

    immigration_legal_help = "immigration_legal_help"
    removal_proceedings = "removal_proceedings"
    asylum = "asylum"
    daca_tps = "daca_tps"
    work_permit = "work_permit"
    green_card = "green_card"
    naturalization = "naturalization"
    change_of_address = "change_of_address"
    fee_waiver = "fee_waiver"
    afghan_specific = "afghan_specific"
    refugee_services = "refugee_services"
    court_notice = "court_notice"
    jury_summons = "jury_summons"
    traffic_court = "traffic_court"
    medical_bill = "medical_bill"
    charity_care = "charity_care"
    insurance_denial = "insurance_denial"
    medicare_appeal = "medicare_appeal"
    medicaid_renewal = "medicaid_renewal"
    prescription_help = "prescription_help"
    primary_care_uninsured = "primary_care_uninsured"
    lab_results = "lab_results"
    vaccine_records = "vaccine_records"
    language_access = "language_access"
    food = "food"
    wic = "wic"
    school_meals = "school_meals"
    snap = "snap"
    ssa_benefits = "ssa_benefits"
    benefits_navigation = "benefits_navigation"
    housing_counseling = "housing_counseling"
    eviction = "eviction"
    rent_assistance = "rent_assistance"
    utility_shutoff = "utility_shutoff"
    section8 = "section8"
    school_enrollment = "school_enrollment"
    special_education = "special_education"
    homeless_students = "homeless_students"
    workers_rights = "workers_rights"
    wage_theft = "wage_theft"
    discrimination = "discrimination"
    workplace_safety = "workplace_safety"
    tax_notice = "tax_notice"
    itin = "itin"
    scam_report = "scam_report"
    crisis = "crisis"
    domestic_violence = "domestic_violence"
    trafficking = "trafficking"
    poison = "poison"


class OrgType(StrEnum):
    """API_CONTRACT §1 — organisation type of a vetted resource."""

    government = "government"
    court = "court"
    nonprofit = "nonprofit"
    legal_aid_lsc = "legal_aid_lsc"
    legal_aid_nonlsc = "legal_aid_nonlsc"
    doj_accredited = "doj_accredited"
    hospital_program = "hospital_program"
    fqhc = "fqhc"
    hotline = "hotline"
    directory = "directory"
    food_bank = "food_bank"
    resettlement = "resettlement"
    utility_program = "utility_program"
    private_directory = "private_directory"


class GeoScope(StrEnum):
    """API_CONTRACT §1 — geographic reach of a resource."""

    national = "national"
    state = "state"
    county = "county"
    city = "city"


class Cost(StrEnum):
    """API_CONTRACT §1 — what a resource costs the user."""

    free = "free"
    sliding = "sliding"
    paid = "paid"
    unknown = "unknown"


class StatusNoteKey(StrEnum):
    """API_CONTRACT §1 — i18n key of a resource status note (``status_note.*``)."""

    lsc_restricted = "lsc_restricted"
    residency_required = "residency_required"
    waitlist = "waitlist"
    appointment_required = "appointment_required"
    hhs_funded_health = "hhs_funded_health"
    not_endorsed = "not_endorsed"
    manual_verify = "manual_verify"


class LinkHealth(StrEnum):
    """API_CONTRACT §1 — last known state of a resource URL."""

    ok = "ok"
    unknown_403 = "unknown_403"
    js_rendered = "js_rendered"
    unverified = "unverified"
    broken = "broken"


class VerificationMethod(StrEnum):
    """API_CONTRACT §1 — how a resource URL was last verified."""

    fetched = "fetched"
    browser = "browser"
    curl_ua = "curl_ua"
    manual_verify = "manual_verify"


class FeedbackKind(StrEnum):
    """API_CONTRACT §1 — kind of "Was this clear?" feedback (D-31)."""

    clear = "clear"
    unclear = "unclear"
    wrong_word = "wrong_word"
    wrong_fact = "wrong_fact"
    offensive = "offensive"
    scam_missed = "scam_missed"
    resource_problem = "resource_problem"


class FeedbackSurface(StrEnum):
    """API_CONTRACT §1 — UI surface the feedback was given on.

    ``app`` is for screens that show no AI output (S18 "Report a problem", Settings → About), so
    those reports do not inflate the ``summary`` counts (DECISIONS §14 CL-028(b)).
    """

    summary = "summary"
    demands = "demands"
    plan = "plan"
    details = "details"
    glossary = "glossary"
    red_flags = "red_flags"
    clerk = "clerk"
    chat = "chat"
    troubleshoot = "troubleshoot"
    resource = "resource"
    language_pack = "language_pack"
    quicksheet = "quicksheet"
    app = "app"


class Platform(StrEnum):
    """API_CONTRACT §1 — client platform reported with feedback."""

    ios = "ios"
    android = "android"
    web = "web"


class ErrorCode(StrEnum):
    """API_CONTRACT §0.1 — machine-readable code of the error envelope."""

    invalid_request = "invalid_request"
    too_many_pages = "too_many_pages"
    pdf_too_long = "pdf_too_long"
    unauthorized = "unauthorized"
    unpaid_tier_real_documents_disabled = "unpaid_tier_real_documents_disabled"
    not_found = "not_found"
    pack_version_mismatch = "pack_version_mismatch"
    payload_too_large = "payload_too_large"
    unsupported_media_type = "unsupported_media_type"
    content_blocked = "content_blocked"
    language_unresolved = "language_unresolved"
    consent_required = "consent_required"
    rate_limited = "rate_limited"
    quota_exhausted = "quota_exhausted"
    internal = "internal"
    model_output_invalid = "model_output_invalid"
    provider_not_configured = "provider_not_configured"
    upstream_unavailable = "upstream_unavailable"
