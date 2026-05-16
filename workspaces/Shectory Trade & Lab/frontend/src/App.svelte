<!-- frontend/src/App.svelte -->
<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import TopBar from './components/TopBar.svelte';
  import RobotsPanel from './components/RobotsPanel.svelte';
  import ChartFrame from './components/ChartFrame.svelte';
  import InstrumentPanel from './components/InstrumentPanel.svelte';
  import BottomBar from './components/BottomBar.svelte';
  import { WsClient } from '$lib/ws';
  import { robotsStore } from '$lib/stores/robots.svelte';

  let labMode = $state(false);
  let selectedRobotId = $state<string | null>(null);
  let ws: WsClient;

  let robots = $derived(robotsStore.all);
  let selectedRobot = $derived(robots.find(r => r.id === selectedRobotId) ?? robots[0] ?? null);

  onMount(() => {
    ws = new WsClient('ws://localhost:8000/ws');
    ws.connect();
  });
  onDestroy(() => ws?.disconnect());
</script>

<div class="shell">
  <TopBar {labMode} onToggleLab={() => labMode = !labMode} />
  <div class="body">
    <RobotsPanel selectedId={selectedRobotId} onSelect={(id) => selectedRobotId = id} />
    <main class="content">
      {#each robots as robot (robot.id)}
        <ChartFrame robotName={robot.name} symbol={robot.symbol} />
      {/each}
    </main>
    <InstrumentPanel info={selectedRobot ? {
      symbol: selectedRobot.symbol,
      priceMin: 20_000,
      priceMax: 30_000,
      margin: 12_400,
      expiration: '17.06.2026',
    } : null} />
  </div>
  <BottomBar events={[]} />
</div>

<style>
  .shell { height: 100%; display: flex; flex-direction: column; }
  .body { flex: 1; display: flex; overflow: hidden; min-height: 0; }
  .content { flex: 1; overflow-y: auto; background: #0f0f1e; display: flex; flex-direction: column; }
</style>
