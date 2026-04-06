import { renderToStaticMarkup } from 'react-dom/server';
import SiteFooter from './SiteFooter';

test('renders Amarktai Network copyright footer', () => {
  const html = renderToStaticMarkup(<SiteFooter />);
  expect(html).toContain('© 2026 Amarktai Network');
});
