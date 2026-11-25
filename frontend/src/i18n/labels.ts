import type { TFunction } from 'i18next'
import type { MealPlan } from '../api/types'

/** The one place that turns a meal plan code into its Ukrainian label (uk.json → meal.*): the
 * catalog filter, the card tag, the tour header and the booking panel all use it. */
export function mealLabel(t: TFunction, plan: MealPlan): string {
  return t(`meal.${plan}`)
}
