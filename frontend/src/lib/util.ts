import type { Difficulty, MatchState, Player } from "../types";

export const DIFF_LABEL: Record<Difficulty, string> = {
  facile: "Facile",
  media: "Media",
  difficile: "Difficile",
};

export function fmtTime(s: number) {
  const t = Math.max(0, Math.ceil(s));
  const m = Math.floor(t / 60);
  const sec = t % 60;
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

export function fmtPts(n: number | null | undefined) {
  if (n == null) return "–";
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

/** Un colore per posto: 0 è chi ha creato la partita. */
export const SEAT_COLORS = ["#2bb3ff", "#ff5d8f", "#3bceac", "#ffb020", "#9b84ff", "#ff8a3d", "#8fd14f", "#f06bd8"];
export const seatColor = (seat: number) => SEAT_COLORS[seat % SEAT_COLORS.length];

export const nameOf = (state: MatchState, seat: number | null | undefined) =>
  state.players.find((p) => p.seat === seat)?.name ?? "?";

/** I giocatori dal primo all'ultimo per punti; a pari punti, per posto. */
export function ranked<T extends { seat: number }>(items: T[], score: (x: T) => number): T[] {
  return [...items].sort((a, b) => score(b) - score(a) || a.seat - b.seat);
}

/** «Daniele», «Daniele e Giulia», «Daniele, Giulia e Marco». */
export function joinNames(names: string[]) {
  if (names.length <= 1) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} e ${names[names.length - 1]}`;
}

export const leaders = (players: Player[]) => {
  const best = Math.max(...players.map((p) => p.total));
  const top = players.filter((p) => p.total === best);
  return best > 0 && top.length < players.length ? new Set(top.map((p) => p.seat)) : new Set<number>();
};

export function fmtDate(epoch: number) {
  return new Date(epoch * 1000).toLocaleDateString("it-IT", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** Riduce la foto nel browser prima di mandarla: dal telefono escono 5-10 MB. */
export async function shrinkImage(file: File, maxSide = 2000): Promise<Blob> {
  try {
    const bmp = await createImageBitmap(file, { imageOrientation: "from-image" } as any);
    const scale = Math.min(1, maxSide / Math.max(bmp.width, bmp.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bmp.width * scale);
    canvas.height = Math.round(bmp.height * scale);
    canvas.getContext("2d")!.drawImage(bmp, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>((r) => canvas.toBlob(r, "image/jpeg", 0.88));
    return blob && blob.size > 0 ? blob : file;
  } catch {
    return file; // HEIC su un browser che non lo apre: ci pensa il server
  }
}

let audio: AudioContext | null = null;
/** Un bip breve: fine del round, ultimo minuto. */
export function beep(freq = 880, ms = 180, times = 1) {
  try {
    audio = audio || new AudioContext();
    for (let i = 0; i < times; i++) {
      const o = audio.createOscillator();
      const g = audio.createGain();
      o.frequency.value = freq;
      o.type = "square";
      g.gain.value = 0.06;
      o.connect(g).connect(audio.destination);
      const t0 = audio.currentTime + i * (ms / 1000 + 0.08);
      o.start(t0);
      o.stop(t0 + ms / 1000);
    }
  } catch {
    /* niente audio */
  }
}

export function buzz(pattern: number | number[]) {
  try {
    navigator.vibrate?.(pattern);
  } catch {
    /* niente vibrazione */
  }
}

export async function share(url: string, text: string) {
  if (navigator.share) {
    try {
      await navigator.share({ title: "Sfida DAS", text, url });
      return "shared";
    } catch {
      /* annullato */
    }
  }
  try {
    await navigator.clipboard.writeText(url);
    return "copied";
  } catch {
    return "failed";
  }
}
