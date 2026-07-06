import { create } from "zustand";

export interface CandidateItem {
  code: string;
  name: string;
  market: string;
  source: string;
  added_at: string;
}

export interface WatchlistItem {
  code: string;
  name: string;
  strategy_name: string;
  state_at_add: string;
  position_at_add: number;
  score_at_add?: number;
  score_details?: Record<string, number>;
  added_at: string;
  scan_job_id?: string;
  current_state?: string;
  current_position?: number;
  current_score?: number;
  current_updated?: string;
  notes?: string;
  tags?: string[];
  ai_analysis?: string;
}

export interface ScanResult {
  code: string;
  name: string;
  state: string;
  position_signal: number;
  date: string;
}

interface OpportunityPoolState {
  candidates: CandidateItem[];
  candidatesLoading: boolean;
  scanning: boolean;
  scanJobId: string | null;
  scanResults: ScanResult[];
  scanProgress: { done: number; total: number; currentCode?: string } | null;
  watchlist: WatchlistItem[];
  watchlistLoading: boolean;

  setCandidates: (candidates: CandidateItem[]) => void;
  setCandidatesLoading: (loading: boolean) => void;
  setScanning: (scanning: boolean) => void;
  setScanJobId: (jobId: string | null) => void;
  setScanResults: (results: ScanResult[]) => void;
  setScanProgress: (progress: { done: number; total: number; currentCode?: string } | null) => void;
  setWatchlist: (watchlist: WatchlistItem[]) => void;
  setWatchlistLoading: (loading: boolean) => void;
  removeFromWatchlist: (code: string) => void;
}

export const useOpportunityPoolStore = create<OpportunityPoolState>((set) => ({
  candidates: [],
  candidatesLoading: false,
  scanning: false,
  scanJobId: null,
  scanResults: [],
  scanProgress: null,
  watchlist: [],
  watchlistLoading: false,

  setCandidates: (candidates) => set({ candidates }),
  setCandidatesLoading: (loading) => set({ candidatesLoading: loading }),
  setScanning: (scanning) => set({ scanning }),
  setScanJobId: (jobId) => set({ scanJobId: jobId }),
  setScanResults: (results) => set({ scanResults: results }),
  setScanProgress: (progress) => set({ scanProgress: progress }),
  setWatchlist: (watchlist) => set({ watchlist }),
  setWatchlistLoading: (loading) => set({ watchlistLoading: loading }),
  removeFromWatchlist: (code) =>
    set((state) => ({
      watchlist: state.watchlist.filter((item) => item.code !== code),
    })),
}));
