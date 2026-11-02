import type { Metadata } from "next";
import Link from "next/link";
import { CalibrationChart } from "@/components/charts/client";
import { Card, EmptyState, PageHeader, Stat } from "@/components/ui/card";
import { Table, Td, Th } from "@/components/ui/table";
import { getBacktest, getCalibration, getModelMeta, getTrackRecord, type TrackRow } from "@/lib/data";
import { dateOnly, num, pct } from "@/lib/format";
import { LEAGUES } from "@/lib/leagues";
import { mean } from "@/lib/metrics";

export const metadata: Metadata = {
  title: "Model performance",
  description: "Public track record of the PitchIQ match predictor (log loss, Brier, RPS, calibration) against bookmaker closing odds, plus the xG model's evaluation.",
};

const MODELS = [
  { key: "ensemble", name: "Ensemble" },
  { key: "dixon_coles", name: "Dixon–Coles" },
  { key: "gbm", name: "LightGBM" },
  { key: "bookmaker", name: "Bookmakers (closing)" },
];
const REPO = "https://github.com/NiKeT972/top5-football-analytics";

function liveSummary(rows: TrackRow[]) {
  return MODELS.filter((m) => m.key !== "bookmaker").map((m) => {
    const r = rows.filter((x) => x.model === m.key && x.book_rps != null);
    return { ...m, n: r.length, logLoss: mean(r.map((x) => x.log_loss)), brier: mean(r.map((x) => x.brier)), rps: mean(r.map((x) => x.rps)), bookLogLoss: mean(r.map((x) => x.book_log_loss)), bookBrier: mean(r.map((x) => x.book_brier)), bookRps: mean(r.map((x) => x.book_rps)) };
  });
}

type XgResults = Record<string, { all_shots: { n: number; log_loss: number; brier: number; auc: number } }>;

export default async function ModelPage() {
  const [track, backtest, calib, xgCalib, xgMeta, predMeta] = await Promise.all([
    getTrackRecord(), getBacktest(), getCalibration("predictor"), getCalibration("xg"), getModelMeta("xg"), getModelMeta("predictor"),
  ]);
  const live = liveSummary(track);
  const ens = live.find((l) => l.key === "ensemble");
  const overall = backtest.filter((b) => b.scope === "all").sort((a, b) => a.rps - b.rps);
  const perLeague = backtest.filter((b) => b.scope === "league_season");
  const seasons = [...new Set(perLeague.map((b) => b.season_id))].sort();
  const xgResults = (xgMeta?.results ?? {}) as XgResults;

  return (
    <div className="space-y-6">
      <PageHeader title="Model performance" subtitle="Every number here is reported as it came out, including where the bookmakers win. Lower is better for log loss, Brier and RPS." />

      <Card title="Live track record" subtitle="Predictions stored before kickoff and committed to a public, timestamped ledger in git">
        {ens && ens.n > 0 ? (
          <>
            <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Stat label="Matches scored" value={ens.n} />
              <Stat label="Ensemble RPS" value={num(ens.rps, 4)} hint={`bookmakers ${num(ens.bookRps, 4)}`} />
              <Stat label="Ensemble log loss" value={num(ens.logLoss, 4)} hint={`bookmakers ${num(ens.bookLogLoss, 4)}`} />
              <Stat label="Ensemble Brier" value={num(ens.brier, 4)} hint={`bookmakers ${num(ens.bookBrier, 4)}`} />
            </div>
            <Table>
              <thead><tr><Th>Model</Th><Th className="text-right">Matches</Th><Th className="text-right">Log loss</Th><Th className="text-right">Brier</Th><Th className="text-right">RPS</Th><Th className="text-right">Bookmaker RPS</Th></tr></thead>
              <tbody>{live.map((l) => <tr key={l.key}><Td className="font-medium">{l.name}</Td><Td className="text-right">{l.n}</Td><Td className="text-right">{num(l.logLoss, 4)}</Td><Td className="text-right">{num(l.brier, 4)}</Td><Td className="text-right">{num(l.rps, 4)}</Td><Td className="text-right">{num(l.bookRps, 4)}</Td></tr>)}</tbody>
            </Table>
          </>
        ) : <EmptyState title="The live record starts with the first finished match after launch">Until then, judge the model by the walk-forward backtest below. Raw predictions: <a className="underline" href={`${REPO}/tree/main/ledger/predictions`}>ledger/predictions</a>.</EmptyState>}
      </Card>

      <Card title="Walk-forward backtest" subtitle={predMeta ? `Seasons ${(predMeta.backtest_seasons as string[]).join(", ")}; models refitted using only data available before each match; scored on ${predMeta.n_evaluated} matches with closing odds` : "Seasons 2023/24 to 2025/26"}>
        {overall.length ? (
          <div className="space-y-5">
            <Table>
              <thead><tr><Th>Model</Th><Th className="text-right">Matches</Th><Th className="text-right">Log loss</Th><Th className="text-right">Brier</Th><Th className="text-right">RPS</Th></tr></thead>
              <tbody>{overall.map((b) => <tr key={b.model}><Td className="font-medium">{MODELS.find((m) => m.key === b.model)?.name ?? b.model}</Td><Td className="text-right">{b.matches}</Td><Td className="text-right">{num(b.log_loss, 4)}</Td><Td className="text-right">{num(b.brier, 4)}</Td><Td className="text-right">{num(b.rps, 4)}</Td></tr>)}</tbody>
            </Table>
            <div>
              <h3 className="mb-2 text-sm font-medium text-fg">RPS by league and season (ensemble / bookmakers)</h3>
              <Table>
                <thead><tr><Th>League</Th>{seasons.map((s) => <Th key={s} className="text-right">{`20${s.slice(0, 2)}/${s.slice(2)}`}</Th>)}</tr></thead>
                <tbody>
                  {LEAGUES.map((l) => (
                    <tr key={l.id}>
                      <Td className="font-medium">{l.name}</Td>
                      {seasons.map((s) => {
                        const e = perLeague.find((b) => b.league_id === l.id && b.season_id === s && b.model === "ensemble");
                        const k = perLeague.find((b) => b.league_id === l.id && b.season_id === s && b.model === "bookmaker");
                        return <Td key={s} className="text-right">{num(e?.rps, 3)} / <span className="text-fg-3">{num(k?.rps, 3)}</span></Td>;
                      })}
                    </tr>
                  ))}
                </tbody>
              </Table>
            </div>
            <div>
              <h3 className="mb-2 text-sm font-medium text-fg">Calibration (backtest)</h3>
              <CalibrationChart rows={calib} models={MODELS} />
            </div>
          </div>
        ) : <EmptyState title="Backtest not published yet" />}
      </Card>

      <Card title="xG model" subtitle="LightGBM vs logistic baseline vs Understat's own xG, on held-out seasons never seen in training">
        {Object.keys(xgResults).length ? (
          <div className="grid gap-6 lg:grid-cols-2">
            <div>
              <Table>
                <thead><tr><Th>Model</Th><Th className="text-right">Shots</Th><Th className="text-right">Log loss</Th><Th className="text-right">Brier</Th><Th className="text-right">ROC-AUC</Th></tr></thead>
                <tbody>{Object.entries(xgResults).map(([name, r]) => <tr key={name}><Td className="font-medium">{name}</Td><Td className="text-right">{r.all_shots.n}</Td><Td className="text-right">{num(r.all_shots.log_loss, 4)}</Td><Td className="text-right">{num(r.all_shots.brier, 4)}</Td><Td className="text-right">{num(r.all_shots.auc, 4)}</Td></tr>)}</tbody>
              </Table>
              <p className="mt-3 text-sm text-fg-2">Penalties use a fixed value equal to the training-set conversion rate ({pct(Number(xgMeta?.penalty_xg ?? NaN), 1)}). Feature importance (SHAP) and full tables are in the <a className="underline" href={`${REPO}/blob/main/pipeline/reports/xg_report.md`}>xG report</a>.</p>
            </div>
            <CalibrationChart rows={xgCalib} models={Object.keys(xgResults).map((k) => ({ key: k, name: k }))} />
          </div>
        ) : <EmptyState title="xG evaluation not published yet" />}
      </Card>

      {track.length > 0 && (
        <Card title="Latest scored predictions">
          <Table>
            <thead><tr><Th>Date</Th><Th>Match</Th><Th className="text-right">H / D / A</Th><Th>Result</Th><Th className="text-right">RPS</Th></tr></thead>
            <tbody>
              {track.filter((t) => t.model === "ensemble").slice(0, 15).map((t) => (
                <tr key={t.match_id}>
                  <Td className="text-fg-2">{dateOnly(t.kickoff_utc)}</Td>
                  <Td><Link className="hover:underline" href={`/match/${t.match_id}`}>{t.home_team} v {t.away_team}</Link></Td>
                  <Td className="text-right">{pct(t.p_home)} / {pct(t.p_draw)} / {pct(t.p_away)}</Td>
                  <Td>{t.result}</Td>
                  <Td className="text-right">{num(t.rps, 3)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>
      )}
    </div>
  );
}
