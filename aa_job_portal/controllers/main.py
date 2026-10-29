# -*- coding: utf-8 -*-
import base64
import calendar as pycalendar
import re
from datetime import date, datetime, time

import pytz
from dateutil.relativedelta import relativedelta
from markupsafe import Markup
from werkzeug.exceptions import NotFound

from odoo import _, fields, http
from odoo.http import request
from odoo.fields import Domain
from odoo.tools import format_date, format_datetime, html2plaintext, plaintext2html

from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.addons.website_hr_recruitment.controllers.main import WebsiteHrRecruitment

PAGE_SIZE = 12
MAX_CV_SIZE = 10 * 1024 * 1024  # 10 MB
CV_EXTENSIONS = ('.pdf', '.doc', '.docx', '.odt', '.rtf', '.txt')

# Lucide-style stroke icons (24x24 viewBox)
ICONS = {
    'grid': '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/>'
            '<rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    'search': '<circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
    'check-square': '<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
    'check': '<polyline points="20 6 9 17 4 12"/>',
    'bookmark': '<path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>',
    'video': '<rect x="2" y="6" width="14" height="12" rx="2"/><polygon points="22 8 16 12 22 16 22 8"/>',
    'calendar': '<rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/>'
                '<line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
    'bell': '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
    'user': '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    'user-check': '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'
                  '<polyline points="16 11 18 13 22 9"/>',
    'sparkles': '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 3v4"/>'
                '<path d="M17 5h4"/>',
    'map-pin': '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>',
    'arrow-right': '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>',
    'arrow-left': '<line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>',
    'x': '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    'menu': '<line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/>'
            '<line x1="3" y1="18" x2="21" y2="18"/>',
    'briefcase': '<rect x="2" y="7" width="20" height="14" rx="2"/>'
                 '<path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>',
    'log-out': '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/>'
               '<line x1="21" y1="12" x2="9" y2="12"/>',
    'globe': '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/>'
             '<path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
    'shield': '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/>',
    'clock': '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    'gauge': '<path d="M12 14l4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/>',
    'upload': '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/>'
              '<line x1="12" y1="3" x2="12" y2="15"/>',
    'target': '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    'check-circle': '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>',
    'alert-circle': '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/>'
                    '<line x1="12" y1="16" x2="12.01" y2="16"/>',
    'x-circle': '<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>',
    'file': '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>',
    'chevron-left': '<polyline points="15 18 9 12 15 6"/>',
    'chevron-right': '<polyline points="9 18 15 12 9 6"/>',
    'external': '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>'
                '<polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>',
    'building': '<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M9 22v-4h6v4"/>'
                '<path d="M8 6h.01M12 6h.01M16 6h.01M8 10h.01M12 10h.01M16 10h.01M8 14h.01M12 14h.01M16 14h.01"/>',
    'inbox': '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/>'
             '<path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
}


def _icon(name, size=20, cls=''):
    paths = ICONS.get(name, ICONS['briefcase'])
    return Markup(
        '<svg class="aajp-ico %s" width="%d" height="%d" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">%s</svg>'
    ) % (cls, size, size, Markup(paths))


class AaJobPortal(http.Controller):

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _partner(self):
        return request.env.user.partner_id

    def _ensure_job_seeker(self):
        partner = self._partner().sudo()
        if not partner.aa_job_seeker:
            partner.aa_job_seeker = True
        return partner

    def _job_domain(self):
        return Domain.AND([
            [('website_published', '=', True)],
            request.env.website.website_domain(),
        ])

    def _get_job(self, job_id):
        job = request.env['hr.job'].sudo().browse(int(job_id)).exists()
        if not job or not job.filtered_domain(self._job_domain()):
            raise NotFound()
        return job

    def _my_applicants(self):
        # Match on the contact only: portal sign-up does not prove ownership of an
        # e-mail address, so e-mail matching could expose someone else's applications.
        return request.env['hr.applicant'].sudo().with_context(active_test=False).search(
            [('partner_id', '=', self._partner().id)], order='create_date desc, id desc')

    def _my_saved(self):
        saved = request.env['aa.job.saved'].sudo().search([('partner_id', '=', self._partner().id)])
        return saved.filtered(lambda s: s.job_id.filtered_domain(self._job_domain()))

    def _my_interviews(self, applicants):
        if not applicants:
            return request.env['calendar.event'].sudo()
        return request.env['calendar.event'].sudo().search(
            [('applicant_id', 'in', applicants.ids)], order='start asc')

    def _my_notifications(self, limit=None, unread_only=False):
        domain = [('partner_id', '=', self._partner().id)]
        if unread_only:
            domain.append(('is_read', '=', False))
        return request.env['aa.job.notification'].sudo().search(domain, limit=limit)

    def _user_tz(self):
        tz_name = request.env.user.tz or request.httprequest.cookies.get('tz') or 'UTC'
        try:
            return pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            return pytz.utc

    def _to_local(self, value):
        if not value:
            return value
        return pytz.utc.localize(value).astimezone(self._user_tz())

    def _fmt_dt(self, value, pattern='EEE, d MMM y · HH:mm'):
        if not value:
            return ''
        return format_datetime(request.env, value, tz=self._user_tz().zone, dt_format=pattern)

    def _fmt_d(self, value, pattern='d MMM y'):
        if not value:
            return ''
        if isinstance(value, datetime):
            value = self._to_local(value).date()
        return format_date(request.env, value, date_format=pattern)

    def _job_location(self, job):
        address = job.address_id
        parts = [address.city, address.country_id.name] if address else []
        parts = [p for p in parts if p]
        if not parts and job.company_id.country_id:
            parts = [job.company_id.country_id.name]
        return ', '.join(parts) or _('Remote / Not specified')

    def _job_snippet(self, job, length=150):
        text = html2plaintext(job.description or '').replace('\n', ' ').strip()
        text = re.sub(r'\s+', ' ', text)
        return text[:length].rstrip() + ('…' if len(text) > length else '')

    def _company_initial(self, company):
        return (company.name or '?').strip()[:1].upper()

    def _employment_type(self, job):
        return job.employee_type_id.name if job.employee_type_id else False

    def _safe_next(self, url, default='/my/jobs'):
        if url and url.startswith('/my/jobs') and '//' not in url:
            return url
        return default

    def _layout_values(self, active):
        partner = self._partner()
        applicants = self._my_applicants()
        return {
            'aajp_partner': partner.sudo(),
            'aajp_active': active,
            'aajp_unread': len(self._my_notifications(unread_only=True)),
            'aajp_applied_count': len(applicants),
            'aajp_applied_job_ids': set(applicants.filtered(lambda a: a.active).job_id.ids),
            'aajp_saved_job_ids': set(self._my_saved().job_id.ids),
            'icon': _icon,
            'job_location': self._job_location,
            'job_snippet': self._job_snippet,
            'company_initial': self._company_initial,
            'employment_type': self._employment_type,
            'fmt_dt': self._fmt_dt,
            'fmt_d': self._fmt_d,
            'to_local': self._to_local,
            'ats_tone': self._ats_tone,
        }

    @staticmethod
    def _ats_tone(grade):
        return {'excellent': 'success', 'good': 'progress', 'fair': 'warning', 'poor': 'danger'}.get(grade, 'muted')

    def _profile_ats(self, partner):
        """Report of the current profile CV, re-checked if the CV changed."""
        partner = partner.sudo()
        report = partner.aa_ats_report_id
        cv = partner.aa_cv_attachment_id
        if cv and (not report or report.attachment_id != cv):
            report = request.env['aa.ats.report'].sudo()._aa_safe_run(cv, partner=partner)
        return report if cv else request.env['aa.ats.report'].sudo()

    def _render(self, template, active, values=None):
        render_values = self._layout_values(active)
        render_values.update(values or {})
        return request.render(template, render_values)

    def _recommended_jobs(self, exclude_ids, limit=6):
        partner = self._partner().sudo()
        jobs = request.env['hr.job'].sudo().search(
            Domain.AND([self._job_domain(), [('id', 'not in', list(exclude_ids))]]),
            order='create_date desc, id desc', limit=80)
        source = ' '.join(filter(None, [partner.aa_headline, partner.aa_skills, partner.function]))
        keywords = {k for k in re.split(r'[\s,;/|]+', source.lower()) if len(k) > 2}
        if not keywords:
            filled = jobs._aa_filled_ids()
            return jobs.filtered(lambda j: j.id not in filled)[:limit]

        def score(job):
            name = (job.name or '').lower()
            desc = html2plaintext(job.description or '').lower()
            return sum(3 * (k in name) + (k in desc) for k in keywords)

        ranked = sorted(jobs, key=score, reverse=True)
        filled = jobs._aa_filled_ids()
        ranked = [j for j in ranked if j.id not in filled]
        return request.env['hr.job'].sudo().browse([j.id for j in ranked[:limit]])

    def _read_cv(self, upload):
        """Validate an uploaded CV. Returns (filename, content, error)."""
        filename = upload.filename or 'cv'
        if not filename.lower().endswith(CV_EXTENSIONS):
            return None, None, _('Please upload your CV as PDF, Word, ODT, RTF or TXT.')
        content = upload.read()
        if not content:
            return None, None, _('The uploaded CV is empty.')
        if len(content) > MAX_CV_SIZE:
            return None, None, _('The CV must be smaller than 10 MB.')
        return filename, content, None

    def _attach(self, filename, content, res_model, res_id):
        return request.env['ir.attachment'].sudo().create({
            'name': filename,
            'raw': content,
            'res_model': res_model,
            'res_id': res_id,
        })

    def _applied_job_ids(self):
        return set(self._my_applicants().filtered('active').job_id.ids)

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------
    @http.route(['/my/jobs', '/my/jobs/dashboard'], type='http', auth='user', website=True)
    def aajp_dashboard(self, **kw):
        partner = self._ensure_job_seeker()
        applicants = self._my_applicants()
        ongoing = applicants.filtered(lambda a: a.application_status == 'ongoing')
        shortlist = ongoing.filtered(lambda a: a.stage_id.aa_portal_shortlist)
        now = fields.Datetime.now()
        interviews = self._my_interviews(applicants).filtered(lambda e: e.stop and e.stop >= now)
        values = {
            'applicants': applicants[:5],
            'stat_applied': len(applicants),
            'stat_saved': len(self._my_saved()),
            'stat_shortlist': len(shortlist),
            'stat_unread': len(self._my_notifications(unread_only=True)),
            'recommended': self._recommended_jobs(set(applicants.job_id.ids)),
            'upcoming_interviews': interviews[:3],
            'show_verify_banner': not partner.aa_profile_verified and not request.session.get('aajp_banner_closed'),
            'ats_report': self._profile_ats(partner),
            'page_title': _('Dashboard'),
        }
        return self._render('aa_job_portal.page_dashboard', 'dashboard', values)

    @http.route('/my/jobs/banner/dismiss', type='http', auth='user', website=True, methods=['POST'])
    def aajp_banner_dismiss(self, **kw):
        request.session['aajp_banner_closed'] = True
        return request.redirect('/my/jobs')

    # ------------------------------------------------------------------
    # Browse / detail
    # ------------------------------------------------------------------
    @http.route(['/my/jobs/browse', '/my/jobs/browse/page/<int:page>'], type='http', auth='user', website=True)
    def aajp_browse(self, page=1, search='', **kw):
        self._ensure_job_seeker()
        Job = request.env['hr.job'].sudo()
        domain = self._job_domain()
        search = (search or '').strip()
        if search:
            domain = Domain.AND([domain, Domain.OR([
                [('name', 'ilike', search)],
                [('description', 'ilike', search)],
                [('department_id.name', 'ilike', search)],
                [('address_id.city', 'ilike', search)],
                [('address_id.country_id.name', 'ilike', search)],
            ])])
        total = Job.search_count(domain)
        pager = portal_pager(url='/my/jobs/browse', total=total, page=page, step=PAGE_SIZE,
                             url_args={'search': search} if search else None)
        jobs = Job.search(domain, order='create_date desc, id desc', limit=PAGE_SIZE, offset=pager['offset'])
        return self._render('aa_job_portal.page_browse', 'browse', {
            'jobs': jobs, 'pager': pager, 'search': search, 'total': total, 'page_title': _('Browse Jobs'),
        })

    @http.route('/my/jobs/job/<int:job_id>', type='http', auth='user', website=True)
    def aajp_job_detail(self, job_id, **kw):
        job = self._get_job(job_id)
        applicant = self._my_applicants().filtered(lambda a: a.job_id == job and a.active)[:1]
        return self._render('aa_job_portal.page_job', 'browse', {
            'job': job, 'my_applicant': applicant, 'page_title': job.name,
            'is_filled': job._aa_is_filled(), 'filled_notice': kw.get('filled'),
        })

    @http.route('/my/jobs/save/<int:job_id>', type='http', auth='user', website=True, methods=['POST'])
    def aajp_toggle_save(self, job_id, next=None, **kw):
        job = self._get_job(job_id)
        Saved = request.env['aa.job.saved'].sudo()
        existing = Saved.search([('partner_id', '=', self._partner().id), ('job_id', '=', job.id)])
        if existing:
            existing.unlink()
        else:
            Saved.create({'partner_id': self._partner().id, 'job_id': job.id})
        return request.redirect(self._safe_next(next, '/my/jobs/saved'))

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------
    @http.route('/my/jobs/apply/<int:job_id>', type='http', auth='user', website=True)
    def aajp_apply_form(self, job_id, **kw):
        partner = self._ensure_job_seeker()
        job = self._get_job(job_id)
        if job._aa_is_filled():
            return request.redirect('/my/jobs/job/%s?filled=1' % job.id)
        if job.id in self._applied_job_ids():
            return request.redirect('/my/jobs/applied?already=1')
        ats_report = self._profile_ats(partner)
        ats_match = ats_report._aa_job_match(job) if ats_report else None
        return self._render('aa_job_portal.page_apply', 'browse', {
            'job': job,
            'ats_report': ats_report,
            'ats_match': ats_match,
            'error': kw.get('error'),
            'default': {
                'phone': partner.phone or ('mobile' in partner._fields and partner.mobile) or '',
                'cover_letter': '',
            },
            'page_title': _('Apply: %s', job.name),
        })

    @http.route('/my/jobs/apply/<int:job_id>/submit', type='http', auth='user', website=True, methods=['POST'])
    def aajp_apply_submit(self, job_id, **post):
        partner = self._ensure_job_seeker()
        job = self._get_job(job_id)
        if job._aa_is_filled():
            return request.redirect('/my/jobs/job/%s?filled=1' % job.id)
        Applicant = request.env['hr.applicant'].sudo()

        if job.id in self._applied_job_ids():
            return request.redirect('/my/jobs/applied?already=1')

        phone = (post.get('phone') or '').strip()
        cover = (post.get('cover_letter') or '').strip()

        def form_error(message):
            return self._render('aa_job_portal.page_apply', 'browse', {
                'job': job, 'error': message,
                'default': {'phone': phone, 'cover_letter': cover},
                'page_title': _('Apply: %s', job.name),
            })

        upload = request.httprequest.files.get('cv_file')
        cv_name = cv_content = None
        if upload and upload.filename:
            cv_name, cv_content, error = self._read_cv(upload)
            if error:
                return form_error(error)
        elif not partner.aa_cv_attachment_id:
            return form_error(_('Please attach your CV.'))

        if phone and not partner.phone:
            partner.phone = phone

        stage = request.env['hr.recruitment.stage'].sudo().search([
            ('fold', '=', False), '|', ('job_ids', '=', False), ('job_ids', '=', job.id),
        ], order='sequence asc', limit=1)
        vals = {
            'partner_id': partner.id,
            'partner_name': partner.name,
            'job_id': job.id,
            'aa_portal_applied': True,
        }
        if 'name' in Applicant._fields and Applicant._fields['name'].required:
            vals['name'] = '%s - %s' % (partner.name, job.name)
        if stage:
            vals['stage_id'] = stage.id
        if job.department_id:
            vals['department_id'] = job.department_id.id
        if job.company_id:
            vals['company_id'] = job.company_id.id
        if cover:
            notes_field = 'description' if 'description' in Applicant._fields else 'applicant_notes'
            if notes_field in Applicant._fields:
                vals[notes_field] = plaintext2html(cover)
        medium = request.env.ref('utm.utm_medium_website', raise_if_not_found=False)
        if medium and 'medium_id' in Applicant._fields:
            vals['medium_id'] = medium.id

        applicant = Applicant.create(vals)
        if phone and not applicant.partner_phone:
            applicant.partner_phone = phone

        if cv_content:
            attachment = self._attach(cv_name, cv_content, 'hr.applicant', applicant.id)
            if post.get('save_cv') or not partner.aa_cv_attachment_id:
                old_cv = partner.aa_cv_attachment_id
                partner.aa_cv_attachment_id = attachment.copy({'res_model': 'res.partner', 'res_id': partner.id})
                if old_cv and old_cv.res_model == 'res.partner':
                    old_cv.unlink()
        else:
            partner.aa_cv_attachment_id.copy({'res_model': 'hr.applicant', 'res_id': applicant.id})

        applicant.message_post(body=Markup('<p>%s</p>') % _('Application submitted from the Candidate Portal.'))
        request.env['aa.job.notification']._aa_notify(
            partner, _('Application submitted: %s', job.name),
            _('We received your application. You will be notified when its status changes.'),
            'application', applicant=applicant, url='/my/jobs/applied')
        return request.redirect('/my/jobs/applied?submitted=1')

    # ------------------------------------------------------------------
    # Applied / Saved
    # ------------------------------------------------------------------
    @http.route('/my/jobs/applied', type='http', auth='user', website=True)
    def aajp_applied(self, status='all', **kw):
        self._ensure_job_seeker()
        applicants = self._my_applicants()
        filters = {
            'all': lambda a: True,
            'active': lambda a: a.application_status == 'ongoing',
            'shortlist': lambda a: a.application_status == 'ongoing' and a.stage_id.aa_portal_shortlist,
            'closed': lambda a: a.application_status != 'ongoing',
        }
        status = status if status in filters else 'all'
        return self._render('aa_job_portal.page_applied', 'applied', {
            'applicants': applicants.filtered(filters[status]),
            'status': status,
            'counts': {k: len(applicants.filtered(f)) for k, f in filters.items()},
            'submitted': kw.get('submitted'),
            'already': kw.get('already'),
            'page_title': _('Applied Jobs'),
        })

    @http.route('/my/jobs/saved', type='http', auth='user', website=True)
    def aajp_saved(self, **kw):
        self._ensure_job_seeker()
        return self._render('aa_job_portal.page_saved', 'saved', {
            'jobs': self._my_saved().job_id, 'page_title': _('Saved Jobs'),
        })

    # ------------------------------------------------------------------
    # Interviews / Calendar
    # ------------------------------------------------------------------
    @http.route('/my/jobs/interviews', type='http', auth='user', website=True)
    def aajp_interviews(self, **kw):
        self._ensure_job_seeker()
        events = self._my_interviews(self._my_applicants())
        now = fields.Datetime.now()
        return self._render('aa_job_portal.page_interviews', 'interviews', {
            'upcoming': events.filtered(lambda e: e.stop and e.stop >= now),
            'past': events.filtered(lambda e: not e.stop or e.stop < now).sorted('start', reverse=True),
            'page_title': _('Interviews'),
        })

    @http.route('/my/jobs/calendar', type='http', auth='user', website=True)
    def aajp_calendar(self, month=None, **kw):
        self._ensure_job_seeker()
        today = self._to_local(fields.Datetime.now()).date()
        try:
            first = datetime.strptime(month, '%Y-%m').date().replace(day=1) if month else today.replace(day=1)
        except ValueError:
            first = today.replace(day=1)

        lang = request.env['res.lang'].sudo().search([('code', '=', request.env.lang or 'en_US')], limit=1)
        week_start = int(lang.week_start or 1) - 1 if lang else 0
        cal = pycalendar.Calendar(firstweekday=week_start)
        weeks = cal.monthdatescalendar(first.year, first.month)

        applicants = self._my_applicants()
        items = {}
        for event in self._my_interviews(applicants):
            day = self._to_local(event.start).date() if event.start else None
            if day:
                items.setdefault(day, []).append({
                    'kind': 'interview', 'label': event.applicant_id.job_id.name or event.name,
                    'time': '' if event.allday else self._fmt_dt(event.start, 'HH:mm'),
                    'url': '/my/jobs/interviews',
                })
        for applicant in applicants:
            day = self._to_local(applicant.create_date).date()
            items.setdefault(day, []).append({
                'kind': 'applied', 'label': applicant.job_id.name or applicant.partner_name,
                'time': '', 'url': '/my/jobs/applied',
            })

        weekday_names = [format_date(request.env, weeks[0][i], date_format='EEE') for i in range(7)]
        return self._render('aa_job_portal.page_calendar', 'calendar', {
            'weeks': weeks, 'month_first': first, 'today': today, 'items': items,
            'weekday_names': weekday_names,
            'month_label': format_date(request.env, first, date_format='MMMM y'),
            'prev_month': (first - relativedelta(months=1)).strftime('%Y-%m'),
            'next_month': (first + relativedelta(months=1)).strftime('%Y-%m'),
            'page_title': _('Calendar'),
        })

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------
    @http.route('/my/jobs/notifications', type='http', auth='user', website=True)
    def aajp_notifications(self, **kw):
        self._ensure_job_seeker()
        return self._render('aa_job_portal.page_notifications', 'notifications', {
            'notifications': self._my_notifications(limit=100), 'page_title': _('Notifications'),
        })

    @http.route('/my/jobs/notifications/<int:notif_id>/open', type='http', auth='user', website=True)
    def aajp_notification_open(self, notif_id, **kw):
        notif = request.env['aa.job.notification'].sudo().browse(notif_id).exists()
        if not notif or notif.partner_id != self._partner():
            raise NotFound()
        notif.is_read = True
        return request.redirect(self._safe_next(notif.url, '/my/jobs/notifications'))

    @http.route('/my/jobs/notifications/read_all', type='http', auth='user', website=True, methods=['POST'])
    def aajp_notifications_read_all(self, **kw):
        self._my_notifications(unread_only=True).write({'is_read': True})
        return request.redirect('/my/jobs/notifications')

    # ------------------------------------------------------------------
    # Profile / CV
    # ------------------------------------------------------------------
    @http.route('/my/jobs/profile', type='http', auth='user', website=True, methods=['GET', 'POST'])
    def aajp_profile(self, **post):
        partner = self._ensure_job_seeker()
        error = saved = False
        if request.httprequest.method == 'POST':
            name = (post.get('name') or '').strip()
            if not name:
                error = _('Your name is required.')
            else:
                try:
                    years = max(0, int(post.get('experience_years') or 0))
                except ValueError:
                    years = 0
                partner.write({
                    'name': name,
                    'phone': (post.get('phone') or '').strip() or False,
                    'aa_headline': (post.get('headline') or '').strip() or False,
                    'aa_skills': (post.get('skills') or '').strip() or False,
                    'aa_experience_years': years,
                    'aa_preferred_location': (post.get('preferred_location') or '').strip() or False,
                    'aa_linkedin_url': (post.get('linkedin_url') or '').strip() or False,
                    'aa_profile_verified': bool(post.get('confirm')),
                })
                upload = request.httprequest.files.get('cv_file')
                if upload and upload.filename:
                    cv_name, cv_content, error = self._read_cv(upload)
                    if cv_content:
                        old = partner.aa_cv_attachment_id
                        partner.aa_cv_attachment_id = self._attach(cv_name, cv_content, 'res.partner', partner.id)
                        if old and old.res_model == 'res.partner':
                            old.unlink()
                saved = not error
        return self._render('aa_job_portal.page_profile', 'profile', {
            'error': error, 'saved': saved, 'page_title': _('My Profile'),
            'ats_report': self._profile_ats(partner),
        })

    # ------------------------------------------------------------------
    # ATS CV check
    # ------------------------------------------------------------------
    @http.route('/my/jobs/ats', type='http', auth='user', website=True)
    def aajp_ats(self, job=None, **kw):
        partner = self._ensure_job_seeker()
        report = self._profile_ats(partner)
        jobs = request.env['hr.job'].sudo().search(self._job_domain(), order='name')
        selected = jobs.filtered(lambda j: str(j.id) == str(job or ''))[:1]
        match = None
        if report and selected:
            score, matched, missing = report._aa_job_match(selected)
            match = {'job': selected, 'score': score, 'matched': matched, 'missing': missing}
        return self._render('aa_job_portal.page_ats', 'ats', {
            'report': report,
            'jobs': jobs,
            'selected_job': selected,
            'match': match,
            'error': kw.get('error'),
            'checked': kw.get('checked'),
            'page_title': _('CV Score (ATS)'),
        })

    @http.route('/my/jobs/ats/upload', type='http', auth='user', website=True, methods=['POST'])
    def aajp_ats_upload(self, **post):
        partner = self._ensure_job_seeker()
        upload = request.httprequest.files.get('cv_file')
        if not upload or not upload.filename:
            return request.redirect('/my/jobs/ats?error=empty')
        cv_name, cv_content, error = self._read_cv(upload)
        if error:
            return request.redirect('/my/jobs/ats?error=format')
        old = partner.aa_cv_attachment_id
        partner.aa_cv_attachment_id = self._attach(cv_name, cv_content, 'res.partner', partner.id)
        if old and old.res_model == 'res.partner':
            old.unlink()
        return request.redirect('/my/jobs/ats?checked=1')

    @http.route('/my/jobs/cv/<int:attachment_id>', type='http', auth='user', website=True)
    def aajp_cv_download(self, attachment_id, **kw):
        attachment = request.env['ir.attachment'].sudo().browse(attachment_id).exists()
        partner = self._partner()
        allowed = attachment and (
            (attachment.res_model == 'res.partner' and attachment.res_id == partner.id)
            or (attachment.res_model == 'hr.applicant' and attachment.res_id in self._my_applicants().ids)
        )
        if not allowed:
            raise NotFound()
        return request.env['ir.binary']._get_stream_from(attachment).get_response(as_attachment=True)


class AaJobPortalHome(CustomerPortal):

    @http.route()
    def home(self, **kw):
        user = request.env.user
        redirect = request.env['ir.config_parameter'].sudo().get_bool('aa_job_portal.redirect_home')
        if redirect and user.share and user.partner_id.sudo().aa_job_seeker:
            return request.redirect('/my/jobs')
        return super().home(**kw)


class AaWebsiteHrRecruitment(WebsiteHrRecruitment):

    @http.route()
    def jobs_apply(self, job, **kwargs):
        """Signed-in candidates never get the public form for a job they already applied to.
        Portal users apply from their dashboard so their saved CV and profile are used."""
        if job.sudo()._aa_is_filled():
            return request.redirect(job.website_url or '/jobs')
        user = request.env.user
        if not user._is_public():
            already = request.env['hr.applicant'].sudo().search_count([
                ('job_id', '=', job.id), ('partner_id', '=', user.partner_id.id)])
            if already:
                return request.redirect('/my/jobs/applied?already=1')
            if user.share:
                return request.redirect('/my/jobs/apply/%s' % job.id)
        return super().jobs_apply(job, **kwargs)
