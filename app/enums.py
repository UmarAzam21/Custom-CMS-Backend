import enum


class ServiceCategory(str, enum.Enum):
    """Matches IServiceItem['category'] in data/appData.tsx"""
    registration = "registration"
    compliance = "compliance"
    licenses = "licenses"


class ServiceType(str, enum.Enum):
    """Matches servicesGridData ids/labels in data/appData.tsx"""
    # registration
    business_ntn = "Business NTN"
    simple_ntn_registration = "Simple NTN Registration"
    business_registration = "Business Registration"
    company_registration = "Company Registration"
    filer_registration = "Filer Registration"
    gst_registration = "GST Registration"

    # compliance
    tax_return_filing = "Tax Return Filing"
    fbr_notices = "FBR Notices"
    wealth_statement = "Wealth Statement"
    dts_registration = "DTS Registration"

    # licenses
    imp_exp_license_psw = "Imp & Exp License (PSW)"
    trade_mark_registration = "Trade Mark Registration"
    pec_registration = "PEC Registration"
    chamber_membership = "Chamber Membership"
    pseb = "PSEB"
    dnfbp = "DNFBP"

    other = "Other"


class ModuleAccess(str, enum.Enum):
    """Access levels for module operations"""
    READ = "read"
    UPDATE = "update"
    ALL = "all"