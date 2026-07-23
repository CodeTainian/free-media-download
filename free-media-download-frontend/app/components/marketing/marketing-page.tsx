import type { Locale } from "../../lib/i18n/locales";
import type { BubbleDictionary } from "../../lib/i18n/messages/en-US";
import { BubbleInput } from "../media-input/bubble-input";
import { ProductPreview } from "./product-preview";
import { SiteFooter } from "./site-footer";
import { SiteHeader } from "./site-header";

const showPricing = process.env.NEXT_PUBLIC_SHOW_PRICING_PREVIEW !== "false";

export function MarketingPage({
  locale,
  dictionary,
}: {
  locale: Locale;
  dictionary: BubbleDictionary;
}) {
  return (
    <>
      <a className="skip-link" href="#main-content">
        {dictionary.common.skipToContent}
      </a>
      <SiteHeader locale={locale} dictionary={dictionary} />
      <main id="main-content">
        <section className="hero-section">
          <div className="hero-copy">
            <p className="hero-eyebrow">
              <span className="status-dot status-dot-brand" aria-hidden="true" />
              {dictionary.hero.eyebrow}
            </p>
            <h1>{dictionary.hero.title}</h1>
            <p className="hero-description">{dictionary.hero.description}</p>
            <div className="hero-proofs" aria-label={dictionary.hero.eyebrow}>
              {dictionary.hero.proofs.map((proof) => (
                <span key={proof}>✓ {proof}</span>
              ))}
            </div>
            <div className="platform-note">
              <span>{dictionary.input.platformDetected}</span>
              <p>{dictionary.hero.platforms}</p>
            </div>
          </div>
          <div className="hero-workbench">
            <div className="bubble-orbit bubble-orbit-one" aria-hidden="true" />
            <div className="bubble-orbit bubble-orbit-two" aria-hidden="true" />
            <BubbleInput />
          </div>
        </section>

        <ProductPreview dictionary={dictionary} />

        <section className="how-section">
          <div className="section-intro">
            <p className="section-kicker">{dictionary.how.eyebrow}</p>
            <h2>{dictionary.how.title}</h2>
          </div>
          <div className="how-grid">
            {dictionary.how.steps.map((step, index) => (
              <article key={step.title}>
                <span className="step-number">{String(index + 1).padStart(2, "0")}</span>
                <div className="step-bubble" aria-hidden="true">
                  {index === 0 ? "↗" : index === 1 ? "✦" : "↘"}
                </div>
                <h3>{step.title}</h3>
                <p>{step.description}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="features-section">
          <div className="section-intro">
            <p className="section-kicker">{dictionary.features.eyebrow}</p>
            <h2>{dictionary.features.title}</h2>
          </div>
          <div className="feature-grid">
            {dictionary.features.items.map((feature, index) => (
              <article key={feature.title}>
                <div className="feature-card-top">
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <small className={`feature-status feature-status-${feature.status}`}>
                    {feature.status === "available"
                      ? dictionary.common.available
                      : dictionary.common.preview}
                  </small>
                </div>
                <div className="feature-symbol" aria-hidden="true">
                  {["◌", "◴", "⌘", "▤", "▦", "→", "文", "◉"][index]}
                </div>
                <h3>{feature.title}</h3>
                <p>{feature.description}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="use-cases-section" id="use-cases">
          <div className="section-intro">
            <p className="section-kicker">{dictionary.useCases.eyebrow}</p>
            <h2>{dictionary.useCases.title}</h2>
          </div>
          <div className="use-case-list">
            {dictionary.useCases.items.map(([title, description], index) => (
              <article key={title}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <h3>{title}</h3>
                <p>{description}</p>
                <i aria-hidden="true">↗</i>
              </article>
            ))}
          </div>
        </section>

        {showPricing ? (
          <section className="pricing-section" id="pricing">
            <div className="section-intro">
              <p className="section-kicker">{dictionary.pricing.eyebrow}</p>
              <h2>{dictionary.pricing.title}</h2>
              <p>{dictionary.pricing.description}</p>
            </div>
            <div className="pricing-grid">
              <article className="pricing-card pricing-card-current">
                <div className="pricing-card-label">
                  <span>{dictionary.pricing.currentName}</span>
                  <small>{dictionary.common.available}</small>
                </div>
                <strong>{dictionary.pricing.currentPrice}</strong>
                <p>{dictionary.pricing.currentNote}</p>
                <ul>
                  {dictionary.pricing.currentFeatures.map((feature) => (
                    <li key={feature}>✓ {feature}</li>
                  ))}
                </ul>
                <a href="#bubble-input">{dictionary.pricing.action} →</a>
              </article>
              <article className="pricing-card pricing-card-future">
                <div className="pricing-card-label">
                  <span>{dictionary.pricing.futureName}</span>
                  <small>{dictionary.common.preview}</small>
                </div>
                <strong>{dictionary.pricing.futurePrice}</strong>
                <p>{dictionary.pricing.futureNote}</p>
                <ul>
                  {dictionary.pricing.futureFeatures.map((feature) => (
                    <li key={feature}>○ {feature}</li>
                  ))}
                </ul>
                <button type="button" disabled>
                  {dictionary.common.comingSoon}
                </button>
              </article>
            </div>
          </section>
        ) : null}

        <section className="faq-section">
          <div className="section-intro">
            <p className="section-kicker">{dictionary.faq.eyebrow}</p>
            <h2>{dictionary.faq.title}</h2>
          </div>
          <div className="faq-list">
            {dictionary.faq.items.map(([question, answer]) => (
              <details key={question}>
                <summary>
                  {question}
                  <span aria-hidden="true">+</span>
                </summary>
                <p>{answer}</p>
              </details>
            ))}
          </div>
        </section>
      </main>
      <SiteFooter locale={locale} dictionary={dictionary} />
    </>
  );
}
