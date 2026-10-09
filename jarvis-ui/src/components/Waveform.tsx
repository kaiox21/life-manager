const BARS = 40;

/** Forma de onda ao vivo do microfone (nível RMS de cada bloco de 64 ms). */
export function Waveform({ levels }: { levels: number[] }) {
  const bars = Array.from({ length: BARS }, (_, i) => levels[levels.length - BARS + i] ?? 0);
  return (
    <div className="wave" role="img" aria-label="Ouvindo">
      {bars.map((v, i) => (
        <span key={i} className="wave__bar" style={{ blockSize: `${Math.min(100, 6 + v * 700)}%` }} />
      ))}
    </div>
  );
}
