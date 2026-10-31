import { Interaction } from '@web/public/interaction';
import { registry } from '@web/core/registry';
import { rpc } from '@web/core/network/rpc';

export class RvsbAccountCta extends Interaction {
    static selector = '.rvsb_account_request';
    dynamicContent = {
        'button[name="rvsb_create_account"]': {
            't-on-click.prevent': this.locked(this.onCreateAccount, true),
        },
    };

    async onCreateAccount() {
        const status = await this.waitFor(rpc('/shop/rvsb/create_account'));
        for (const block of this.el.querySelectorAll('[data-rvsb-status]')) {
            block.classList.toggle('d-none', block.dataset.rvsbStatus !== status);
        }
    }
}

registry
    .category('public.interactions')
    .add('rvsb_checkout_account.account_cta', RvsbAccountCta);
