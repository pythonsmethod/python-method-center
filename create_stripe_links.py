# -*- coding: utf-8 -*-
# create_stripe_links.py
# Run once to create Stripe products and Payment Links
# Usage: STRIPE_SECRET_KEY=sk_live_... python create_stripe_links.py

import os
import stripe

stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')

  if not stripe.api_key:
  raise ValueError('STRIPE_SECRET_KEY env var is required')

    # ---- Product 1: Tariff 1 ----
    product1 = stripe.Product.create(
          name='Python Method - Tariff Znakomstvo',
          description='Individualnoe soprovozhdenie po metodu Karena Dzhangiryana. 6 nedel.',
    )

    price1 = stripe.Price.create(
      product=product1['id'],
            unit_amount=111300,
            currency='usd',
      )

        link1 = stripe.PaymentLink.create(
          line_items=[{'price': price1['id'], 'quantity': 1}],
                  billing_address_collection='required',
                  after_completion={
                        'type': 'hosted_confirmation',
                        'hosted_confirmation': {
                              'custom_message': (
                                    'Spasibo za oplatu! Vernites v Telegram bot - '
                                    's vami uzhe vykhodyat na svyaz.'
                  )
                }
              },
            )

              # ---- Product 2: Tariff 2 ----
              product2 = stripe.Product.create(
                    name='Python Method - Polnoe soprovozhdenie',
                    description='Individualnoe soprovozhdenie po metodu Karena Dzhangiryana. 21 nedelya.',
              )

              price2 = stripe.Price.create(
                product=product2['id'],
                      unit_amount=472500,
                      currency='usd',
                )

                  link2 = stripe.PaymentLink.create(
                    line_items=[{'price': price2['id'], 'quantity': 1}],
                            billing_address_collection='required',
                            after_completion={
                                  'type': 'hosted_confirmation',
                                  'hosted_confirmation': {
                                        'custom_message': (
                                              'Spasibo za oplatu! Vernites v Telegram bot - '
                                              's vami uzhe vykhodyat na svyaz.'
                            )
                          }
                        },
                      )

                        print('TARIFF_1_LINK=' + link1['url'])
                            print('TARIFF_2_LINK=' + link2['url'])
                                
