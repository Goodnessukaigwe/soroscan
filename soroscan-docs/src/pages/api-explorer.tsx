import React from 'react';
import BrowserOnly from '@docusaurus/BrowserOnly';
import Layout from '@theme/Layout';

function RedocContainer(): React.JSX.Element {
  React.useEffect(() => {
    if (document.querySelector('script[data-redoc]')) {
      return;
    }
    const script = document.createElement('script');
    script.src = 'https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js';
    script.defer = true;
    script.setAttribute('data-redoc', 'true');
    document.body.appendChild(script);
  }, []);

  return React.createElement('redoc', {'spec-url': '/openapi.yaml'} as Record<string, string>);
}

export default function ApiExplorerPage(): React.JSX.Element {
  return (
    <Layout
      title="API Explorer"
      description="Interactive explorer for the SoroScan OpenAPI specification.">
      <main style={{padding: '1rem 0'}}>
        <div className="container">
          <h1>API Explorer</h1>
          <p>
            Explore and test SoroScan endpoints interactively. The explorer is loaded
            client-side to keep static builds stable.
          </p>
          <BrowserOnly fallback={<p>Loading API explorer...</p>}>
            {() => <RedocContainer />}
          </BrowserOnly>
        </div>
      </main>
    </Layout>
  );
}
