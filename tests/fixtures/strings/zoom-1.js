{
          "id": "5119451176108032",
          "category": "other",
          "apiName": "20917322331_url_targeting_for_hotfix_bonsai_url_tracking_params",
          "name": null,
          "staticConditions": ["and", ["or", {
            "match": "simple",
            "type": "url",
            "value": "https://zoom.us/bonsai"
          }]],
          "deactivationEnabled": false,
          "undoOnDeactivation": false,
          "tags": [],
          "activationType": "callback",
          "activationCode": function callbackFn() {
            const endUTC = Date.UTC(2026, 3, 1, 8, 0, 0);
            // Apr 1, 2026 12am PST
            const nowUTC = Date.now();
            if (nowUTC > endUTC)
              return;

            const PRICING_TRACKING_PARAMS = {
              fpr: 'zoom',
              utm_source: 'zoom',
              utm_medium: 'pricing-page'
            };
            const HD_TRACKING_PARAMS = {
              fpr: 'zoom',
              utm_source: 'zoom',
              utm_medium: 'home-destination'
            };

            function addTrackingParams(urlString, trackingParams) {
              const urlObj = new URL(urlString);
              Object.entries(trackingParams).forEach(function([key,value]) {
                urlObj.searchParams.set(key, value);
              });
              return urlObj.toString();
            }

            function setupBonsaiXHRInterceptor(urlPattern, responsePath, trackingParams, options) {
              const originalXHROpen = XMLHttpRequest.prototype.open;
              const originalXHRSend = XMLHttpRequest.prototype.send;

              XMLHttpRequest.prototype.open = function(method, url) {
                this._interceptUrl = url;
                return originalXHROpen.apply(this, arguments);
              }
              ;

              XMLHttpRequest.prototype.send = function() {
                const xhr = this;
                if (xhr._interceptUrl && xhr._interceptUrl.includes(urlPattern)) {
                  const originalOnReadyStateChange = xhr.onreadystatechange;
                  xhr.onreadystatechange = function() {
                    if (xhr.readyState === 4) {
                      try {
                        const response = JSON.parse(xhr.responseText);
                        const pathParts = responsePath.split('.');
                        let target = response;
                        for (let i = 0; i < pathParts.length - 1 && target; i++) {
                          target = target[pathParts[i]];
                        }
                        const urlValue = target && target[pathParts[pathParts.length - 1]];
                        if (urlValue) {
                          let finalUrl = addTrackingParams(urlValue, trackingParams);
                          if (options && options.useBonsaiUtmContentFromStorage) {
                            const bonsaiUtmContent = sessionStorage.getItem('bonsaiUtmContent');
                            if (bonsaiUtmContent) {
                              const urlObj = new URL(finalUrl);
                              urlObj.searchParams.set('utm_content', bonsaiUtmContent);
                              finalUrl = urlObj.toString();
                            }
                          }
                          if (options && options.removeUtmContent) {
                            const urlObj = new URL(finalUrl);
                            urlObj.searchParams.delete('utm_content');
                            finalUrl = urlObj.toString();
                          }
                          target[pathParts[pathParts.length - 1]] = finalUrl;
                          Object.defineProperty(xhr, 'responseText', {
                            value: JSON.stringify(response),
                            configurable: true
                          });
                          Object.defineProperty(xhr, 'response', {
                            value: JSON.stringify(response),
                            configurable: true
                          });
                        }
                      } catch (e) {// Ignore parse errors
                      }
                    }
                    if (originalOnReadyStateChange) {
                      originalOnReadyStateChange.apply(this, arguments);
                    }
                  }
                  ;
                }
                return originalXHRSend.apply(this, arguments);
              }
              ;
            }

            if (location.pathname.includes('/pricing')) {
              function setup() {
                if (window.campaignFlags.isLoggedIn) {
                  // CASE 3 - Intercept /billing/bonsai/customer/manage
                  setupBonsaiXHRInterceptor('/billing/bonsai/customer/manage', 'result.url', PRICING_TRACKING_PARAMS, {
                    removeUtmContent: true
                  });
                  // CASE 2 - Keep track Pricing Page was visited
                  sessionStorage.setItem('bonsaiLastVisit', 'pricing');
                } else {
                  // CASE 1 - Intercept /billing/basic/config
                  setupBonsaiXHRInterceptor('/billing/basic/config', 'result.defaultBonsaiUrl', PRICING_TRACKING_PARAMS, {
                    removeUtmContent: true
                  });
                }
              }

              const utils = window['optimizely'].get('utils');
              utils.observeSelector('link[href*="/fe-pricing-new-design/"],link[href*="/fe-pricing-v3/"]', function(linkElm) {
                if (linkElm.href.includes('/fe-pricing-new-design/') && location.pathname.includes('/pricing/bonsai')) {
                  setup();
                } else if (linkElm.href.includes('/fe-pricing-v3/')) {
                  setup();
                }
              }, {
                once: true
              });

            } else if (location.pathname.includes('/opc/buy') && location.search.includes('type=buy_trial') && location.search.includes('from=bonsai')) {
              // CASE 4 - Intercept /billing/bonsai/customer/initialize
              if (location.search.includes('itm_source=homedestination')) {
                setupBonsaiXHRInterceptor('/billing/bonsai/customer/initialize', 'result.url', HD_TRACKING_PARAMS, {
                  useBonsaiUtmContentFromStorage: true
                });
              } else if (sessionStorage.getItem('bonsaiLastVisit') === 'pricing') {
                setupBonsaiXHRInterceptor('/billing/bonsai/customer/initialize', 'result.url', PRICING_TRACKING_PARAMS, {
                  removeUtmContent: true
                });
              }
            } else {
              sessionStorage.removeItem('bonsaiLastVisit');
            }
          }
        }