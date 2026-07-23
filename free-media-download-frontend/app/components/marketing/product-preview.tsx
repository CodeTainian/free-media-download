import type { BubbleDictionary } from "../../lib/i18n/messages/en-US";

export function ProductPreview({ dictionary }: { dictionary: BubbleDictionary }) {
  return (
    <section className="product-preview-section" id="product">
      <div className="section-intro">
        <p className="section-kicker">{dictionary.preview.eyebrow}</p>
        <h2>{dictionary.preview.title}</h2>
        <p>{dictionary.preview.description}</p>
      </div>

      <div className="preview-window" aria-label={dictionary.preview.title}>
        <header>
          <div className="preview-window-brand">
            <span className="preview-avatar" aria-hidden="true">
              B
            </span>
            <div>
              <strong>Bubble Workspace</strong>
              <small>{dictionary.preview.videoMeta}</small>
            </div>
          </div>
          <span className="preview-badge">{dictionary.common.preview}</span>
        </header>
        <div className="preview-tabs" aria-label={dictionary.preview.title}>
          {dictionary.preview.tabs.map((tab, index) => (
            <span className={index === 0 ? "active" : ""} key={tab}>
              {tab}
              {index > 1 ? <small>{dictionary.common.preview}</small> : null}
            </span>
          ))}
        </div>
        <div className="preview-grid">
          <aside className="preview-source">
            <div className="preview-video">
              <span aria-hidden="true">▶</span>
              <i />
              <i />
            </div>
            <strong>{dictionary.preview.videoTitle}</strong>
            <small>{dictionary.preview.videoMeta}</small>
            <div className="preview-source-pills">
              <span>18:42</span>
              <span>EN</span>
            </div>
          </aside>
          <main className="preview-summary">
            <p className="section-kicker">{dictionary.workspace.overview}</p>
            <h3>{dictionary.workspace.summaryHeading}</h3>
            <p>{dictionary.preview.overview}</p>
            <div className="preview-key-points">
              {dictionary.preview.keyPoints.map((point, index) => (
                <article key={point}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <strong>{point}</strong>
                </article>
              ))}
            </div>
          </main>
          <aside className="preview-chapters">
            <p className="section-kicker">{dictionary.workspace.tabs.chapters}</p>
            <ol>
              {dictionary.preview.chapters.map((chapter, index) => (
                <li key={chapter}>
                  <span>{["01:20", "07:21", "13:22"][index]}</span>
                  <strong>{chapter}</strong>
                </li>
              ))}
            </ol>
            <div className="preview-mind-map" aria-hidden="true">
              <i />
              <i />
              <i />
              <span>AI</span>
            </div>
          </aside>
        </div>
      </div>
    </section>
  );
}
