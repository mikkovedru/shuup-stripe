# -*- coding: utf-8 -*-
# This file is part of Shuup Stripe Addon.
#
# Copyright (c) 2012-2018, Shoop Commerce Ltd. All rights reserved.
#
# This source code is licensed under the OSL-3.0 license found in the
# LICENSE file in the root directory of this source tree.
from django.utils.translation import ugettext as _
from shuup.utils.excs import Problem

from shuup_stripe.utils import get_amount_info


def _handle_stripe_error(charge_data):
    error_dict = charge_data.get("error")
    if error_dict:
        raise Problem("Error! Stripe: %(message)s (%(type)s)." % error_dict)
    failure_code = charge_data.get("failure_code")
    failure_message = charge_data.get("failure_message")
    if failure_code or failure_message:
        raise Problem(
            _("Stripe: %(failure_message)s (%(failure_code)s).") % charge_data
        )


class StripeCharger(object):
    identifier = "stripe"
    name = _("Stripe Checkout")

    def __init__(self, secret_key, order):
        self.secret_key = secret_key
        self.order = order

    def _send_request(self):
        stripe_token = self.order.payment_data["stripe"].get("token")
        stripe_customer = self.order.payment_data["stripe"].get("customer")
        input_data = {
            "description": _("Payment for order {id} on {shop}").format(
                id=self.order.identifier, shop=self.order.shop,
            )
        }
        if stripe_token:
            input_data["source"] = stripe_token
        elif stripe_customer:
            input_data["customer"] = stripe_customer

        input_data.update(get_amount_info(self.order.taxful_total_price))

        from shuup.utils.http import retry_request
        return retry_request(
            method="post",
            url="https://api.stripe.com/v1/charges",
            data=input_data,
            auth=(self.secret_key, ""),
            headers={
                "Idempotency-Key": self.order.key,
                "Stripe-Version": "2015-04-07"
            }
        )

    def create_charge(self):
        resp = self._send_request()
        charge_data = resp.json() if hasattr(resp, "json") else resp
        _handle_stripe_error(charge_data)
        if not charge_data.get("paid"):
            raise Problem(_("Stripe Charge does not say 'paid'."))

        return self.order.create_payment(
            self.order.taxful_total_price,
            payment_identifier="Stripe-%s" % charge_data["id"],
            description=_("Stripe Charge")
        )
