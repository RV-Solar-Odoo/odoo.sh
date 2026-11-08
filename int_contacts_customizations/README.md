# Contacts Customizations

Sales sends a dealer a portal account email from the contact. On the opportunity, CRM Customizations opens a wizard first so the same email also sets the pricelist and the RVSB Dealer tag.

## Send account setup email

On a contact, **Send account setup email**:

- No portal login yet: create one and email the standard create-password link.
- A login exists but they have never signed in: email that link again.
- They already signed in, including after creating an account at checkout: email them to sign in with that same login. No second account is created.
- The email already belongs to a different contact: do not create a second login. The note names that contact so the dealer pricelist goes on it.

Retail guests still create an account from the order confirmation page. That is `rvsb_checkout_account`, and this button does not change it.

The button is limited to sales users. An internal user's email is refused.
