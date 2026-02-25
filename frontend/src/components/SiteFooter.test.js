import { renderToStaticMarkup } from 'react-dom/server';
import SiteFooter from './SiteFooter';

test('renders Amarktai Network footer', () => {
  const html = renderToStaticMarkup(<SiteFooter />);
  expect(html).toContain('Amarktai Network');
});
