import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { ArtifactTabs } from "../app/components/workspace/artifact-tabs";
import { enUS } from "../app/lib/i18n/messages/en-US";
import type { ArtifactKind } from "../app/lib/workspace/types";

function TabsHarness() {
  const [active, setActive] = useState<ArtifactKind>("summary");
  return <ArtifactTabs active={active} onChange={setActive} dictionary={enUS} />;
}

describe("ArtifactTabs", () => {
  it("supports arrows, Home, End, Enter and correct ARIA state", async () => {
    const user = userEvent.setup();
    render(<TabsHarness />);

    const summary = screen.getByRole("tab", { name: "Summary" });
    summary.focus();
    expect(summary.getAttribute("aria-selected")).toBe("true");
    expect(summary.tabIndex).toBe(0);

    await user.keyboard("{ArrowRight}");
    const chapters = screen.getByRole("tab", { name: "Chapters" });
    expect(document.activeElement).toBe(chapters);
    expect(chapters.getAttribute("aria-selected")).toBe("true");

    await user.keyboard("{End}");
    const transcript = screen.getByRole("tab", { name: /Transcript/ });
    expect(document.activeElement).toBe(transcript);
    expect(transcript.getAttribute("aria-selected")).toBe("true");

    await user.keyboard("{Home}");
    expect(document.activeElement).toBe(summary);

    await user.keyboard("{ArrowLeft}");
    expect(document.activeElement).toBe(transcript);

    await user.keyboard("{Enter}");
    expect(transcript.getAttribute("aria-selected")).toBe("true");
  });
});
