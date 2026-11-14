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

## Portal role and sales rep

**Portal role** is on the contact, under Sales. Owner and Accountant can see credit, invoices, payments, and store credit. Buyer can order and cannot see those. Viewer can see orders and tracking. Existing contacts stay Owner. The owner manages logins at My Portal → Users. The last owner cannot be demoted or disabled. Changing a role signs that person out.

My addresses has three tabs: My Business Locations, My Billing Addresses, and Customer Addresses (drop-ship), each with a count. A business location can be moved to Customer Addresses from its card; customer addresses have no move link (change it in the address form). The open tab is kept in the address (`?tab=`), and adding or editing an address returns to that tab. Add Address on Customer Addresses starts the form as a customer address. Each card lists the address with tags (Business or Customer, Commercial or Residential, Loading dock, Forklift) styled like the shop's product tags; checkout cards show the same tags. A residential address clears the dock and forklift. The company address stays a business location. Viewers and accountants can look, and cannot edit.

**Your Sales Rep** is at the top of My Portal. It uses the salesperson on the company contact, so an extra login sees the same person. Email and phone are links. The card is hidden when no salesperson is set. Phone uses `work_phone` when that field exists, otherwise phone, otherwise mobile.
