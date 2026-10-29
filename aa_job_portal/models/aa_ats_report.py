# -*- coding: utf-8 -*-
import json
import logging

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.tools import html2plaintext

from . import ats_engine

_logger = logging.getLogger(__name__)

CV_EXTENSIONS = ('.pdf', '.doc', '.docx', '.odt', '.rtf', '.txt')
GRADES = [('excellent', 'ATS-ready'), ('good', 'Good'), ('fair', 'Needs work'), ('poor', 'Not ATS-friendly')]
CATEGORIES = [
    ('file', 'File & format'),
    ('contact', 'Contact details'),
    ('sections', 'Standard sections'),
    ('layout', 'Layout & formatting'),
    ('content', 'Content quality'),
]


class AaAtsReport(models.Model):
    _name = 'aa.ats.report'
    _description = 'CV ATS Compliance Report'
    _order = 'create_date desc, id desc'

    name = fields.Char('File', required=True)
    attachment_id = fields.Many2one('ir.attachment', 'CV File', ondelete='cascade', index=True)
    partner_id = fields.Many2one('res.partner', 'Candidate', ondelete='cascade', index=True)
    applicant_id = fields.Many2one('hr.applicant', 'Applicant', ondelete='cascade', index=True)
    job_id = fields.Many2one('hr.job', 'Job Position', ondelete='set null')
    score = fields.Integer('ATS Score', help='ATS compliance score out of 100.')
    grade = fields.Selection(GRADES, 'ATS Grade')
    keyword_score = fields.Integer('Job Match %', help='Share of the job description keywords found in the CV.')
    has_keywords = fields.Boolean('Matched Against a Job')
    matched_keywords = fields.Char('Matched Keywords')
    missing_keywords = fields.Char('Missing Keywords')
    file_format = fields.Char('Format')
    word_count = fields.Integer('Words')
    page_count = fields.Integer('Pages')
    passed_count = fields.Integer('Passed')
    warning_count = fields.Integer('Warnings')
    failed_count = fields.Integer('Failed')
    checks_json = fields.Text('Checks')
    cv_text = fields.Text('Extracted Text', help='Plain text an ATS can read from the file.')
    report_html = fields.Html('Report', compute='_compute_report_html', sanitize=False)

    # ------------------------------------------------------------------
    # Presentation helpers (portal and backend)
    # ------------------------------------------------------------------
    def _aa_checks(self):
        self.ensure_one()
        try:
            return json.loads(self.checks_json or '[]')
        except ValueError:
            return []

    def _aa_grouped_checks(self):
        checks = self._aa_checks()
        groups = []
        for key, label in CATEGORIES:
            items = [c for c in checks if c.get('category') == key]
            if items:
                groups.append({
                    'key': key, 'label': label, 'checks': items,
                    'points': sum(c['points'] for c in items), 'max': sum(c['max'] for c in items),
                })
                groups[-1]['pct'] = round(100.0 * groups[-1]['points'] / groups[-1]['max']) if groups[-1]['max'] else 0
        return groups

    def _aa_tips(self, limit=5):
        """Most valuable fixes first: failures, then warnings, by lost points."""
        checks = [c for c in self._aa_checks() if c.get('status') != 'pass' and c.get('tip')]
        checks.sort(key=lambda c: (c['status'] != 'fail', -(c['max'] - c['points'])))
        return checks[:limit]

    def _aa_grade_label(self):
        return dict(GRADES).get(self.grade, '')

    def _aa_matched(self):
        return [k for k in (self.matched_keywords or '').split('|') if k]

    def _aa_missing(self):
        return [k for k in (self.missing_keywords or '').split('|') if k]

    @api.depends('checks_json', 'score', 'keyword_score', 'matched_keywords', 'missing_keywords')
    def _compute_report_html(self):
        icons = {'pass': ('✔', '#16a34a'), 'warn': ('!', '#d97706'), 'fail': ('✖', '#dc2626')}
        for report in self:
            parts = []
            for group in report._aa_grouped_checks():
                rows = []
                for c in group['checks']:
                    sym, color = icons.get(c['status'], ('•', '#6b7280'))
                    tip = Markup('<div style="color:#6b7280;font-size:12px;">%s</div>') % c['tip'] if c.get('tip') and c['status'] != 'pass' else ''
                    rows.append(Markup(
                        '<tr><td style="width:28px;color:%s;font-weight:700;vertical-align:top;">%s</td>'
                        '<td style="vertical-align:top;"><b>%s</b> — %s%s</td>'
                        '<td style="text-align:right;white-space:nowrap;vertical-align:top;color:#6b7280;">%s / %s</td></tr>'
                    ) % (color, sym, c['title'], c['message'], tip, c['points'], c['max']))
                parts.append(Markup(
                    '<h4 style="margin:14px 0 6px;font-size:14px;">%s <span style="color:#6b7280;font-weight:400;">'
                    '(%s / %s)</span></h4><table class="table table-sm mb-0">%s</table>'
                ) % (group['label'], group['points'], group['max'], Markup('').join(rows)))
            if report.has_keywords:
                chips = Markup('').join(
                    Markup('<span class="badge rounded-pill text-bg-success me-1 mb-1">%s</span>') % k for k in report._aa_matched())
                miss = Markup('').join(
                    Markup('<span class="badge rounded-pill text-bg-danger me-1 mb-1">%s</span>') % k for k in report._aa_missing())
                parts.insert(0, Markup(
                    '<h4 style="margin:4px 0 6px;font-size:14px;">Job keyword match: %s%%</h4>'
                    '<div>%s</div><div class="mt-1">%s</div>') % (report.keyword_score, chips, miss))
            report.report_html = Markup('').join(parts)

    # ------------------------------------------------------------------
    # Running a check
    # ------------------------------------------------------------------
    @api.model
    def _aa_job_keywords(self, job):
        if not job:
            return []
        text = ' '.join(filter(None, [
            html2plaintext(job.description or '') if 'description' in job._fields else '',
            job.requirements or '' if 'requirements' in job._fields else '',
        ]))
        return ats_engine.job_keywords(job.name or '', text)

    @api.model
    def _aa_is_cv(self, attachment):
        return bool(attachment) and (attachment.name or '').lower().endswith(CV_EXTENSIONS)

    @api.model
    def _aa_run(self, attachment, partner=False, applicant=False, job=False):
        """Analyse a CV attachment, store the report and return it (sudo)."""
        attachment = attachment.sudo()
        if not self._aa_is_cv(attachment):
            return self.browse()
        raw = attachment.raw
        raw = bytes(getattr(raw, 'content', raw) or b'')  # Odoo 18+ returns a BinaryBytes wrapper
        job = job or (applicant.job_id if applicant else False)
        name = (applicant.partner_name if applicant else False) or (partner.name if partner else '') or ''
        result = ats_engine.analyse(attachment.name, raw, name, self._aa_job_keywords(job))
        statuses = [c['status'] for c in result['checks']]
        report = self.sudo().create({
            'name': attachment.name,
            'attachment_id': attachment.id,
            'partner_id': partner.id if partner else (applicant.partner_id.id if applicant else False),
            'applicant_id': applicant.id if applicant else False,
            'job_id': job.id if job else False,
            'score': result['score'],
            'grade': result['grade'],
            'has_keywords': 'keyword_score' in result,
            'keyword_score': result.get('keyword_score', 0),
            'matched_keywords': '|'.join(result.get('matched', [])),
            'missing_keywords': '|'.join(result.get('missing', [])),
            'file_format': result['format'],
            'word_count': result['word_count'],
            'page_count': result['page_count'],
            'passed_count': statuses.count('pass'),
            'warning_count': statuses.count('warn'),
            'failed_count': statuses.count('fail'),
            'checks_json': json.dumps(result['checks']),
            'cv_text': result['text'],
        })
        if applicant:
            applicant.sudo().with_context(aa_skip_ats=True).write({'aa_ats_report_id': report.id})
        if partner and not applicant:
            partner.invalidate_recordset(['aa_ats_report_id', 'aa_ats_score', 'aa_ats_grade'])
        return report

    @api.model
    def _aa_safe_run(self, attachment, **kwargs):
        try:
            with self.env.cr.savepoint():
                return self._aa_run(attachment, **kwargs)
        except Exception:
            _logger.warning('ATS check failed for attachment %s', attachment.id, exc_info=True)
            return self.browse()

    def _aa_job_match(self, job):
        """Live match of this report's CV text against another job: (score, matched, missing)."""
        self.ensure_one()
        return ats_engine.keyword_match(self.cv_text or '', self._aa_job_keywords(job))

    def action_open_cv(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': '/web/content/%s?download=true' % self.attachment_id.id, 'target': 'self'}
