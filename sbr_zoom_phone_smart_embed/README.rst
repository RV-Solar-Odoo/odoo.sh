==============================
Odoo x Zoom Phone Smart Embed
==============================

.. |badge1| image:: https://img.shields.io/badge/maturity-Production-green.png
    :target: https://odoo-community.org/page/development-status
    :alt: Production/Stable
.. |badge2| image:: https://img.shields.io/badge/license-OPL--1-blue.png
    :target: https://www.tldrlegal.com/license/open-public-license-v1-0-opl-1-0
    :alt: License: OPL-1
.. |badge3| image:: https://img.shields.io/badge/version-19.0.1.0.0-informational.png
    :alt: Version: 19.0.1.0.0

|badge1| |badge2| |badge3|

This module integrates `Zoom Phone Smart Embed <https://developers.zoom.us/docs/zoom-phone/smart-embed/>`_
directly into the Odoo backend interface, enabling users to make and receive calls via Zoom Phone
without ever leaving Odoo. A draggable floating bubble provides always-accessible access to the
embedded Zoom dialer, and call logs are automatically posted to the related Odoo record when a
call ends.

**Table of Contents**

.. contents::
   :local:

Features
========

* **Floating Zoom Phone Bubble** — A draggable systray bubble renders the embedded Zoom Phone
  dialer anywhere on screen. The bubble persists globally across all Odoo views.
* **One-click dialing from phone fields** — Clicking any phone number field in form view
  opens the Zoom dialer and optionally auto-dials the number directly.
* **SMS via Zoom Phone** — The SMS button on phone fields is patched to pre-fill the Zoom
  SMS composer with the recipient's number.
* **Automatic call log posting** — When a call ends, a formatted call log entry (caller,
  callee, timestamp, and call status) is automatically posted as a chatter message on the
  currently active record.
* **Auto Dial toggle** — Configurable option to either immediately place the call or simply
  pre-fill the dialer and let the user confirm.
* **In-app call notifications** — Optional Odoo notification alerts for incoming/outgoing
  call events, displayed natively in the Odoo interface.
* **Viewport-aware dragging** — The floating panel and bubble can be freely repositioned
  and are constrained to always remain within the visible viewport, including on window resize.

Requirements
============

* Odoo **19.0**
* A valid **Zoom Phone** license and a configured Zoom application with Smart Embed enabled.
* The Odoo instance's origin domain must be whitelisted in the Zoom Developer Console as an
  allowed origin for the Smart Embed iframe.

Dependencies
============

This module depends on the following Odoo apps:

* ``web`` — Core web framework (OWL, RPC, systray registry)
* ``mail`` — Chatter and ``message_post`` for call log entries
* ``sms`` — ``SendSMSButton`` component patching for Zoom SMS integration

Installation
============

1. Copy the ``sbr_zoom_phone_smart_embed`` folder into your Odoo ``addons`` path.
2. Restart the Odoo server.
3. Activate **Developer Mode** (*Settings > General Settings > Developer Tools*).
4. Go to *Apps*, click **Update Apps List**, then search for **Zoom Phone Smart Embed** and
   install it.

Configuration
=============

Zoom Developer Console
----------------------

Before using the module, ensure your Zoom application is configured correctly:

1. Log in to the `Zoom App Marketplace <https://marketplace.zoom.us/>`_ and open your
   Smart Embed application.
2. Under **Allowed Domains / Origins**, add your Odoo instance's base URL
   (e.g., ``https://your-odoo.example.com``).
3. Save the application settings.

Odoo Settings
-------------

1. Go to *Settings > General Settings*.
2. Scroll to the **Zoom Phone** section (or search for "Zoom Phone").
3. Configure the following options:

   * **Enable Auto Dial** — When enabled, clicking a phone field link will immediately
     initiate the call inside Zoom Phone. When disabled, Zoom Phone will pre-fill the
     number in the dialer so the user can review and dial manually.
   * **Enable Notification** — When enabled, Odoo will display in-app notifications
     for call events (e.g., incoming call alerts) directly within the interface.

4. Click **Save**.

Usage
=====

Making a Call from a Phone Field
---------------------------------

1. Open any record that contains a phone field (e.g., a Contact, Lead, or Customer).
2. Click the phone number link in the field.
3. The Zoom Phone bubble opens automatically, pre-filled with the number.
4. If **Auto Dial** is enabled, the call is placed immediately. Otherwise, review the
   number in the Zoom dialer and click the call button manually.

Sending an SMS via Zoom Phone
------------------------------

1. Open a record with a phone field that shows the SMS icon.
2. Click the SMS icon next to the phone number.
3. The Zoom Phone panel opens with the SMS composer pre-filled with the recipient's number.
4. Compose and send your message from within the Zoom interface.

Using the Floating Bubble Manually
------------------------------------

* **Open/Close** — Click the Zoom Phone bubble icon (bottom-right by default) to toggle
  the Zoom Phone panel.
* **Drag to reposition** — Click and drag the bubble or the panel header to move it
  anywhere on screen. The widget stays within the viewport boundaries at all times.
* **Close panel** — Click the **×** button in the panel header to collapse the dialer.

Automatic Call Log
------------------

When a call ends, the module listens for the ``zp-call-ended-event`` postMessage from
the Zoom iframe. If the Zoom Phone was opened from a specific record (via a phone field
click), a formatted chatter message is automatically posted to that record containing:

* Call status (Completed ✅ / Missed ❌ / Rejected 🚫)
* Caller and callee names or phone numbers
* Date and time of the call

Credits
=======

Authors
-------

* `Softberry Tech `_

Contributors
------------

* Softberry Tech Development Team

Maintainers
-----------

This module is maintained by **Softberry Tech**.

For support or feature requests, please contact us at support@softberrytech.com.

License
=======

This module is distributed under the **OPL-1** (Odoo Proprietary License v1.0).
See `<https://www.odoo.com/documentation/user/legal/licenses.html#odoo-apps>`_ for full
license terms.