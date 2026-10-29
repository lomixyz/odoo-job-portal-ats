# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .aa_ats_report import GRADES


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    @api.model_create_multi
    def create(self, vals_list):
        attachments = super().create(vals_list)
        if not self.env.context.get('aa_skip_ats'):
            Report = self.env['aa.ats.report']
            for att in attachments:
                if att.res_model == 'hr.applicant' and att.res_id and Report._aa_is_cv(att):
                    applicant = self.env['hr.applicant'].sudo().browse(att.res_id).exists()
                    if applicant:
                        Report._aa_safe_run(att, applicant=applicant)
        return attachments


class HrApplicant(models.Model):
    _inherit = 'hr.applicant'

    aa_ats_report_id = fields.Many2one('aa.ats.report', 'ATS Report', copy=False, ondelete='set null')
    aa_ats_score = fields.Integer('ATS Score', related='aa_ats_report_id.score', store=True)
    aa_ats_grade = fields.Selection(GRADES, 'ATS Grade', related='aa_ats_report_id.grade', store=True)
    aa_ats_keyword_score = fields.Integer('Job Match %', related='aa_ats_report_id.keyword_score', store=True)
    aa_ats_report_html = fields.Html(related='aa_ats_report_id.report_html')
    aa_ats_report_ids = fields.One2many('aa.ats.report', 'applicant_id', 'ATS History')

    def action_aa_run_ats(self):
        Report = self.env['aa.ats.report']
        for applicant in self:
            atts = self.env['ir.attachment'].sudo().search(
                [('res_model', '=', 'hr.applicant'), ('res_id', '=', applicant.id)], order='create_date desc, id desc')
            cv = atts.filtered(Report._aa_is_cv)[:1]
            if not cv:
                raise UserError(_('No CV file (PDF, DOCX, ODT, RTF or TXT) is attached to %s.', applicant.display_name))
            Report._aa_run(cv, applicant=applicant)
        return True

    def action_aa_open_ats_cv(self):
        self.ensure_one()
        return self.aa_ats_report_id.action_open_cv() if self.aa_ats_report_id else False


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Computed, not stored: res.partner is read on every page (login included), so this
    # module never adds a column there that a code update without "-u" could be missing.
    aa_ats_report_id = fields.Many2one('aa.ats.report', 'CV ATS Report', compute='_compute_aa_ats_report_id')
    aa_ats_score = fields.Integer('CV ATS Score', compute='_compute_aa_ats_report_id')
    aa_ats_grade = fields.Selection(GRADES, 'CV ATS Grade', compute='_compute_aa_ats_report_id')

    @api.depends('aa_cv_attachment_id')
    def _compute_aa_ats_report_id(self):
        Report = self.env['aa.ats.report'].sudo()
        for partner in self:
            cv = partner.sudo().aa_cv_attachment_id
            report = Report.search([('partner_id', '=', partner.id), ('applicant_id', '=', False),
                                    ('attachment_id', '=', cv.id)], limit=1) if cv else Report
            partner.aa_ats_report_id = report
            partner.aa_ats_score = report.score
            partner.aa_ats_grade = report.grade

    def write(self, vals):
        res = super().write(vals)
        if vals.get('aa_cv_attachment_id') and not self.env.context.get('aa_skip_ats'):
            Report = self.env['aa.ats.report']
            for partner in self:
                Report._aa_safe_run(partner.aa_cv_attachment_id, partner=partner)
        return res
