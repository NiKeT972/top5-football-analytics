import type { Metadata } from "next";
import { Card, PageHeader } from "@/components/ui/card";

export const metadata: Metadata = {
  title: "Methodology & sources",
  description: "How PitchIQ's xG model, match predictor, expected points and player similarity work; data sources and limitations.",
};

const REPO = "https://github.com/NiKeT972/top5-football-analytics";

export default function About() {
  return (
    <div className="space-y-6">
      <PageHeader title="Methodology, sources & limitations" subtitle="Everything on this site is reproducible from the open-source pipeline." />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Expected goals (xG)">
          <div className="space-y-2 text-sm text-fg-2">
            <p>A LightGBM classifier (with a logistic-regression baseline) trained on every Understat shot in the top five leagues since 2014/15. Features: distance and the angle the goal mouth subtends (Understat coordinates converted to metres on a 105×68 m pitch), situation, body part, the action before the shot, game state and minute.</p>
            <p>Penalties get a fixed value equal to the historical conversion rate. Own goals are not shots and get no xG. The model is evaluated on whole held-out seasons (log loss, Brier, ROC-AUC, calibration) and compared with Understat&apos;s own xG.</p>
          </div>
        </Card>
        <Card title="Match predictor">
          <div className="space-y-2 text-sm text-fg-2">
            <p><b>Dixon–Coles</b> (one per league): Poisson goals with team attack and defence strengths, home advantage, a low-score correction and exponential time decay. Promoted teams start from the historical average of promoted sides.</p>
            <p><b>LightGBM</b> on pre-match features: Elo difference, rolling xG for/against over the last 10 matches, goals, form and rest days.</p>
            <p>The <b>ensemble</b> averages the two with a weight chosen only on earlier seasons. Backtests are walk-forward (models never see the future) and are compared with bookmaker closing odds after removing the margin with Shin&apos;s method.</p>
          </div>
        </Card>
        <Card title="Expected points (xPts)">
          <p className="text-sm text-fg-2">Each match is replayed 10,000 times, treating every shot as an independent chance that scores with probability equal to its xG. That gives each team a probability of winning, drawing and losing, and expected points = 3·P(win) + P(draw). The xPts table sums these over the season.</p>
        </Card>
        <Card title="Player similarity">
          <p className="text-sm text-fg-2">Outfield players with at least 900 minutes are described by per-90 npxG, xA, shots, key passes, xGChain, xGBuildup, non-penalty goals, assists and npxG per shot. Profiles are standardised within each season and position group, reduced with PCA and compared by cosine similarity; radars show percentiles among the same group across all five leagues. Players are matched across sources by fuzzy name matching within each team-season.</p>
        </Card>
        <Card title="Ask (natural-language data questions)">
          <p className="text-sm text-fg-2">A language model writes one SQL query against documented, read-only views. The query is parsed and only a single SELECT on whitelisted views is allowed; it runs as a database role that can only read those views, with a 5-second timeout and a 200-row limit. The SQL is always shown. A daily request cap keeps it free to run.</p>
        </Card>
        <Card title="Data sources (thank you)">
          <ul className="list-disc space-y-1 pl-5 text-sm text-fg-2">
            <li><a className="underline" href="https://understat.com">Understat</a>: fixtures, results, shots and player stats.</li>
            <li><a className="underline" href="https://www.football-data.co.uk">football-data.co.uk</a>: results and betting odds.</li>
            <li><a className="underline" href="http://clubelo.com">ClubElo</a>: Elo ratings.</li>
            <li><a className="underline" href="https://fbref.com">FBref</a>: player age, nationality and position.</li>
            <li>Scraping via the <a className="underline" href="https://github.com/probberechts/soccerdata">soccerdata</a> project&apos;s approach: rate-limited, cached, incremental, never re-downloading data we already have.</li>
          </ul>
          <p className="mt-2 text-xs text-fg-3">All data belongs to its providers. PitchIQ shows derived analytics only and does not offer raw-data downloads.</p>
        </Card>
      </div>
      <Card title="Limitations">
        <ul className="list-disc space-y-1 pl-5 text-sm text-fg-2">
          <li>Free event data has no freeze frames (defender and goalkeeper positions), so xG cannot see how open a chance really was.</li>
          <li>Defensive actions (tackles, interceptions, pressures) are not in the free sources, so defensive profiles in Scout are weak.</li>
          <li>Rest days count league matches only (cups and European games are missing).</li>
          <li>Upset alerts and edges are disagreements with the market, not betting advice. The market is very hard to beat.</li>
          <li>The live track record only starts on launch day; earlier performance comes from the walk-forward backtest.</li>
        </ul>
        <p className="mt-3 text-sm text-fg-2">Code, model reports and the prediction ledger: <a className="underline" href={REPO}>{REPO.replace("https://", "")}</a>.</p>
      </Card>
    </div>
  );
}
