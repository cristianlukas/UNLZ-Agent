import { NextResponse } from "next/server";
import os from "os";

export async function GET() {
  const cpus = os.cpus();
  const cpuModel = cpus[0].model;

  // Calculate CPU usage (instantaneous approximation)
  const cpuUsage = cpus.map((cpu) => {
    const total = Object.values(cpu.times).reduce((acc, tv) => acc + tv, 0);
    return 100 - (100 * cpu.times.idle) / total;
  });
  const avgCpuUsage = cpuUsage.reduce((a, b) => a + b, 0) / cpuUsage.length;

  const totalMem = os.totalmem();
  const freeMem = os.freemem();
  const usedMem = totalMem - freeMem;
  const memUsagePercent = (usedMem / totalMem) * 100;

  return NextResponse.json({
    cpu: {
      model: cpuModel,
      usagePercent: Math.round(avgCpuUsage),
      cores: cpus.length,
    },
    memory: {
      totalGb: (totalMem / 1024 ** 3).toFixed(1),
      usedGb: (usedMem / 1024 ** 3).toFixed(1),
      usagePercent: Math.round(memUsagePercent),
    },
    gpu: {
      // Node.js doesn't have native GPU stats, returning simulated for Native GUI feel
      model: "NVIDIA GeForce RTX 3060 (Simulated)",
      usagePercent: Math.floor(Math.random() * 20) + 10, // Simulated fluctuation
      memoryTotal: 12288,
      memoryUsed: 4096,
    },
  });
}
