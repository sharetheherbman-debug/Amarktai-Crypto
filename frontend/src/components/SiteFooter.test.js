import { renderToStaticMarkup } from 'react-dom/server';
import SiteFooter from './SiteFooter';

test('renders Amarktai Crypto copyright footer', () => {
  const year = new Date().getFullYear();
  const html = renderToStaticMarkup(<SiteFooter />);
  expect(html).toContain(`© ${year} Amarktai Crypto`);
});
