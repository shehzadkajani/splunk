require(["jquery","underscore","splunkjs/mvc/simplexml/ready!","collections/services/saved/Searches"],function(__WEBPACK_EXTERNAL_MODULE__0__,__WEBPACK_EXTERNAL_MODULE__1__,__WEBPACK_EXTERNAL_MODULE__2__,__WEBPACK_EXTERNAL_MODULE__12__){return function(modules){var installedModules={};function __webpack_require__(moduleId){if(installedModules[moduleId])return installedModules[moduleId].exports;var module=installedModules[moduleId]={i:moduleId,l:!1,exports:{}};return modules[moduleId].call(module.exports,module,module.exports,__webpack_require__),module.l=!0,module.exports}return __webpack_require__.m=modules,__webpack_require__.c=installedModules,__webpack_require__.d=function(exports,name,getter){__webpack_require__.o(exports,name)||Object.defineProperty(exports,name,{enumerable:!0,get:getter})},__webpack_require__.r=function(exports){"undefined"!=typeof Symbol&&Symbol.toStringTag&&Object.defineProperty(exports,Symbol.toStringTag,{value:"Module"}),Object.defineProperty(exports,"__esModule",{value:!0})},__webpack_require__.t=function(value,mode){if(1&mode&&(value=__webpack_require__(value)),8&mode)return value;if(4&mode&&"object"==typeof value&&value&&value.__esModule)return value;var ns=Object.create(null);if(__webpack_require__.r(ns),Object.defineProperty(ns,"default",{enumerable:!0,value:value}),2&mode&&"string"!=typeof value)for(var key in value)__webpack_require__.d(ns,key,function(key){return value[key]}.bind(null,key));return ns},__webpack_require__.n=function(module){var getter=module&&module.__esModule?function(){return module.default}:function(){return module};return __webpack_require__.d(getter,"a",getter),getter},__webpack_require__.o=function(object,property){return Object.prototype.hasOwnProperty.call(object,property)},__webpack_require__.p="",__webpack_require__(__webpack_require__.s="splunk_monitoring_console-extensions/forwarder_monitoring_extension")}({0:function(module,exports){module.exports=__WEBPACK_EXTERNAL_MODULE__0__},1:function(module,exports){module.exports=__WEBPACK_EXTERNAL_MODULE__1__},12:function(module,exports){module.exports=__WEBPACK_EXTERNAL_MODULE__12__},2:function(module,exports){module.exports=__WEBPACK_EXTERNAL_MODULE__2__},"splunk_monitoring_console-extensions/forwarder_monitoring_extension":function(module,exports,__webpack_require__){var __WEBPACK_AMD_DEFINE_ARRAY__,__WEBPACK_AMD_DEFINE_RESULT__;__WEBPACK_AMD_DEFINE_ARRAY__=[__webpack_require__(0),__webpack_require__(1),__webpack_require__(12),__webpack_require__(2)],void 0===(__WEBPACK_AMD_DEFINE_RESULT__=function($,_,SavedSearchCollection){var savedSearchCollection=new SavedSearchCollection;savedSearchCollection.fetch({data:{app:"splunk_monitoring_console",owner:"-",search:'name="DMC Forwarder - Build Asset Table"'}}).done(function(){savedSearchCollection.models[0].entry.content.get("disabled")?($(".fieldset").hide(),$(".dashboard-row").hide(),$("#forwarder_monitoring_extension").show()):$("#forwarder_monitoring_extension").hide()}).fail(function(){$("#forwarder_monitoring_extension").html(_("Cannot find the saved search: DMC Forwarder - Build Asset Table").t()).show()})}.apply(exports,__WEBPACK_AMD_DEFINE_ARRAY__))||(module.exports=__WEBPACK_AMD_DEFINE_RESULT__)}})});