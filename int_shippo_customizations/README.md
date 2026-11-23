# Shippo Customizations

Buys Shippo labels from warehouse deliveries and quotes UPS and FedEx Ground, 2 Day and Overnight at website checkout.

## Settings

Inventory → Settings → Shippo: API token, test mode reminder, Freight over (lb), and Shippo Boxes.

## Website quotes

- **Boxes.** The quote uses the smallest Shippo Box the cart fits. A cart that doesn't fit one box is packed heaviest first into as many boxes as it needs, each under its own weight limit and the carriers' 150 lb. An item too big for every box goes as its own parcel in its own dimensions.
- **Freight.** Carts heavier than Freight over (500 lb by default; 0 turns the weight check off), carts that need more than 20 boxes, and carts with an item over 150 lb are offered only "Freight: We'll Quote Shipping" ($0) and store pickup. Confirming one posts a note and gives the salesperson a Quote freight activity. Staff add the freight charge before it ships.
- **Nothing ships now.** When every product in the cart is backordered (`sale.order.line._int_shipping_quote_qty` is 0 for all of them), checkout offers only "Ships When Backorder Arrives" ($0) and store pickup. That shipping is invoiced with the backorder.
- Both $0 methods are ordinary fixed-price methods with a **Checkout role** on the shipping method form. Backend quotations can use them at any time.

## Decisions made during build

- 2026-11-23: freight is a stand-in until the freight feature is built. The 500 lb limit is a placeholder (SPEC decision 38).
- The $0 methods use their own "Shipping (charged later)" product, because a fixed-price method writes its price to its product.
