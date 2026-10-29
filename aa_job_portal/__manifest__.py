# -*- coding: utf-8 -*-
{
    'name': 'Job Portal - Candidate Portal & Recruitment Dashboard',
    'version': '17.0.1.5.2',
    'category': 'Human Resources/Recruitment',
    'summary': 'Candidate self-service job portal on the website and a Recruitment '
               'dashboard inside Odoo for recruiters',
    'description': """
Candidate Job Portal
====================
Portal users who sign up on the website get a dedicated job-seeker dashboard:

* Dashboard with applied / saved / shortlisted / notification counters
* Recommended jobs matched to the candidate profile
* Browse published jobs, save them, and apply in one step with a CV
* Applied jobs with live status, interviews and a monthly calendar
* In-portal notifications for status changes and scheduled interviews
* Candidate profile with CV, skills and a verification step
* Welcome popup on the website once per sign-in, and a highlighted Candidate Dashboard menu
* One application per job: the public apply page and form block duplicates

ATS CV check (Applicant Tracking System compliance):

* Every CV is scored out of 100 against ATS-compliant résumé rules: file format and readability,
  contact details, standard sections, single-column layout without tables/images/text boxes,
  standard fonts, length, dates, bullets, action verbs, quantified results, personal data
* Job keyword match % with matched and missing keywords for each application
* Candidates see their report and fix tips in the portal; recruiters see scores on applicants

Recruiters (Recruitment Officer / Manager) get Recruitment > Dashboard inside Odoo:

* KPIs: published jobs, applications in progress, new this week, upcoming interviews, hired this month
* Job positions table with publish switch, pipeline size, new applicants and hired vs. target
* Pipeline-by-stage chart, latest applications and upcoming interviews
* Every item opens the standard Odoo views (job form, applicant kanban/form, calendar)
""",
    'author': 'Allam Bushra',
    'website': 'https://www.linkedin.com/in/lomixyz/',
    'license': 'LGPL-3',
    'depends': ['website_hr_recruitment', 'portal', 'auth_signup', 'calendar'],
    'data': [
        'security/ir.model.access.csv',
        'data/aa_job_portal_data.xml',
        'views/portal_icons.xml',
        'views/portal_layout.xml',
        'views/portal_pages.xml',
        'views/portal_welcome.xml',
        'views/portal_ats.xml',
        'views/portal_home.xml',
        'views/backend_views.xml',
        'views/recruitment_dashboard_views.xml',
        'views/ats_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'aa_job_portal/static/src/scss/job_portal.scss',
        ],
        'web.assets_backend': [
            'aa_job_portal/static/src/recruitment_dashboard/recruitment_dashboard.js',
            'aa_job_portal/static/src/recruitment_dashboard/recruitment_dashboard.xml',
            'aa_job_portal/static/src/recruitment_dashboard/recruitment_dashboard.scss',
        ],
    },
    'images': ['static/description/banner.png'],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': True,
}
