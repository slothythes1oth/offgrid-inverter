// Single ECharts registration point: tree-shaken imports only, so the bundle
// carries exactly the chart types the app uses. Every chart goes through
// this module + theme.js (SPEC 8A: one theme, one product).

import { BarChart, LineChart } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  MarkAreaComponent,
  MarkLineComponent,
  MarkPointComponent,
  TooltipComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([
  LineChart,
  BarChart,
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  MarkLineComponent,
  MarkAreaComponent,
  MarkPointComponent,
  CanvasRenderer,
]);

export default echarts;
