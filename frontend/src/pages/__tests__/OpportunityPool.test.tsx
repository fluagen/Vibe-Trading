import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { OpportunityPool } from "../OpportunityPool";

describe("OpportunityPool page", () => {
  it("renders two tabs: scan center and watchlist", () => {
    render(
      <MemoryRouter>
        <OpportunityPool />
      </MemoryRouter>
    );

    expect(screen.getByRole("tab", { name: /scan/i })).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: /watchlist|watching|观察|候选/i })
    ).toBeInTheDocument();
  });
});
