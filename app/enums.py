import enum

class ServiceType(str, enum.Enum):
    web_development = "Web Development"
    seo = "SEO"
    graphic_design = "Graphic Design"
    digital_marketing = "Digital Marketing"
    app_development = "App Development"
    content_writing = "Content Writing"
    other = "Other"