require(["jquery","underscore","splunkjs/mvc/simplexml/ready!","backbone","splunkjs/mvc","splunkjs/mvc/tableview","splunkjs/mvc/searchmanager","splunkjs/mvc/postprocessmanager"],function(__WEBPACK_EXTERNAL_MODULE__0__,__WEBPACK_EXTERNAL_MODULE__1__,__WEBPACK_EXTERNAL_MODULE__2__,__WEBPACK_EXTERNAL_MODULE__3__,__WEBPACK_EXTERNAL_MODULE__5__,__WEBPACK_EXTERNAL_MODULE__6__,__WEBPACK_EXTERNAL_MODULE__8__,__WEBPACK_EXTERNAL_MODULE__23__){return function(modules){var installedModules={};function __webpack_require__(moduleId){if(installedModules[moduleId])return installedModules[moduleId].exports;var module=installedModules[moduleId]={i:moduleId,l:!1,exports:{}};return modules[moduleId].call(module.exports,module,module.exports,__webpack_require__),module.l=!0,module.exports}return __webpack_require__.m=modules,__webpack_require__.c=installedModules,__webpack_require__.d=function(exports,name,getter){__webpack_require__.o(exports,name)||Object.defineProperty(exports,name,{enumerable:!0,get:getter})},__webpack_require__.r=function(exports){"undefined"!=typeof Symbol&&Symbol.toStringTag&&Object.defineProperty(exports,Symbol.toStringTag,{value:"Module"}),Object.defineProperty(exports,"__esModule",{value:!0})},__webpack_require__.t=function(value,mode){if(1&mode&&(value=__webpack_require__(value)),8&mode)return value;if(4&mode&&"object"==typeof value&&value&&value.__esModule)return value;var ns=Object.create(null);if(__webpack_require__.r(ns),Object.defineProperty(ns,"default",{enumerable:!0,value:value}),2&mode&&"string"!=typeof value)for(var key in value)__webpack_require__.d(ns,key,function(key){return value[key]}.bind(null,key));return ns},__webpack_require__.n=function(module){var getter=module&&module.__esModule?function(){return module.default}:function(){return module};return __webpack_require__.d(getter,"a",getter),getter},__webpack_require__.o=function(object,property){return Object.prototype.hasOwnProperty.call(object,property)},__webpack_require__.p="",__webpack_require__(__webpack_require__.s="splunk_monitoring_console-extensions/splunk_tcpin_performance_extension")}({0:function(module,exports){module.exports=__WEBPACK_EXTERNAL_MODULE__0__},1:function(module,exports){module.exports=__WEBPACK_EXTERNAL_MODULE__1__},2:function(module,exports){module.exports=__WEBPACK_EXTERNAL_MODULE__2__},23:function(module,exports){module.exports=__WEBPACK_EXTERNAL_MODULE__23__},3:function(module,exports){module.exports=__WEBPACK_EXTERNAL_MODULE__3__},5:function(module,exports){module.exports=__WEBPACK_EXTERNAL_MODULE__5__},6:function(module,exports){module.exports=__WEBPACK_EXTERNAL_MODULE__6__},8:function(module,exports){module.exports=__WEBPACK_EXTERNAL_MODULE__8__},"splunk_monitoring_console-extensions/splunk_tcpin_performance_extension":function(module,exports,__webpack_require__){var __WEBPACK_AMD_DEFINE_ARRAY__,__WEBPACK_AMD_DEFINE_RESULT__;__WEBPACK_AMD_DEFINE_ARRAY__=[__webpack_require__(1),__webpack_require__(0),__webpack_require__(3),__webpack_require__(23),__webpack_require__(8),__webpack_require__(6),__webpack_require__(5),__webpack_require__(2)],void 0===(__WEBPACK_AMD_DEFINE_RESULT__=function(_,$,Backbone,PostProcessManager,SearchManager,TableView,mvc){var HTML_CELL_KPI_PERCENT_FILL_GOOD=_.template('<div class=kpi-cell"><span class="icon icon-check"></span> <%= value %></div>'),HTML_CELL_KPI_PERCENT_FILL_OK=_.template('<div class=kpi-cell"><span class="icon icon-minus"></span> <%= value %></div>'),HTML_CELL_KPI_PERCENT_FILL_BAD=_.template('<div class=kpi-cell"><span class="icon icon-x"></span> <%= value %></div>'),parseFillPercAsFloat=function(string){return parseFloat(string.match(/(pset\d+:\s)?(\d+\.\d+)/)[2])},CustomCellRendererKpiFillPerc=TableView.BaseCellRenderer.extend({canRender:function(cellData){return"Queue Fill Ratio (Last 1 Minute)"==cellData.field||"Queue Fill Ratio (Last 10 Minutes)"==cellData.field},render:function($td,cellData){var parsedValues=[],html="";$td.addClass("numeric"),_.isArray(cellData.value)?_.each(cellData.value,function(cellValue){parsedValues.push({displayValue:cellValue,fillPerc:parseFillPercAsFloat(cellValue)})}):parsedValues.push({displayValue:cellData.value,fillPerc:parseFillPercAsFloat(cellData.value)}),_.each(parsedValues,function(value){value.fillPerc<60?html+=HTML_CELL_KPI_PERCENT_FILL_GOOD({value:value.displayValue}):value.fillPerc>=60&&value.fillPerc<80?html+=HTML_CELL_KPI_PERCENT_FILL_OK({value:value.displayValue}):value.fillPerc>80&&(html+=HTML_CELL_KPI_PERCENT_FILL_BAD({value:value.displayValue}))}),$td.html(html)}});mvc.Components.get("snapshotTcpInFillRatioTable").getVisualization(function(tableView){tableView.table.addCellRenderer(new CustomCellRendererKpiFillPerc),tableView.table.render()})}.apply(exports,__WEBPACK_AMD_DEFINE_ARRAY__))||(module.exports=__WEBPACK_AMD_DEFINE_RESULT__)}})});