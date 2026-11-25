// What the booking wizard hands to the payment page (spec 05). Router state, so it lives only for
// this navigation; the payment page reads the order itself from the API.

export function payPath(orderId: number): string {
  return `/orders/${orderId}/pay`
}

export interface PayPageState {
  /**
   * Confirm recalculates the price with today's rate and freezes it (backend confirm_order). When
   * the frozen total differs from the total shown on step 4, both go to the payment page, which
   * shows «Ціну оновлено за курсом на сьогодні» with the old and the new amount before the pay
   * button (spec 05).
   */
  priceChanged?: { shown: string; frozen: string }
}
