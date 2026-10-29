/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class AaRecruitmentDashboard extends Component {
    static template = "aa_job_portal.RecruitmentDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ data: null, filter: "all", search: "" });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call("hr.job", "aa_recruitment_dashboard_data", []);
    }

    visibleJobs() {
        const term = this.state.search.trim().toLowerCase();
        return this.state.data.jobs.filter((job) => {
            if (this.state.filter === "published" && !job.published) {
                return false;
            }
            if (this.state.filter === "unpublished" && job.published) {
                return false;
            }
            return !term || `${job.name} ${job.department} ${job.recruiter}`.toLowerCase().includes(term);
        });
    }

    hiredPct(job) {
        return job.target ? Math.min(100, Math.round((100 * job.hired) / job.target)) : 0;
    }

    setFilter(filter) {
        this.state.filter = filter;
    }

    onSearch(ev) {
        this.state.search = ev.target.value;
    }

    async togglePublish(job) {
        await this.orm.call("hr.job", "aa_dashboard_toggle_publish", [[job.id]]);
        await this.load();
    }

    async open(kind, resId = false) {
        const action = await this.orm.call("hr.job", "aa_dashboard_action", [kind, resId]);
        if (action) {
            await this.action.doAction(action);
        }
    }
}

registry.category("actions").add("aa_recruitment_dashboard", AaRecruitmentDashboard);
