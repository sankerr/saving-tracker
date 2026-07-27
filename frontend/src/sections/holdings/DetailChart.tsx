import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import { t } from '../../copy';
import { fmtIls } from '../../lib/format';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
);

type Point = { label: string; value: number };

export default function DetailChart({
  series,
  height = 180,
}: {
  series: Point[];
  height?: number;
}) {
  if (!series.length) return <p className="muted">—</p>;
  return (
    <div className="chart-wrap chart-wrap--small" style={{ height }}>
      <Line
        data={{
          labels: series.map((p) => p.label),
          datasets: [
            {
              label: t('section.dashboard'),
              data: series.map((p) => p.value),
              borderColor: '#6E5FE0',
              backgroundColor: 'rgba(110,95,224,0.12)',
              fill: true,
              tension: 0.25,
              pointRadius: 0,
            },
          ],
        }}
        options={{
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { maxTicksLimit: 6 } },
            y: { ticks: { callback: (v) => fmtIls(Number(v)) } },
          },
        }}
      />
    </div>
  );
}
