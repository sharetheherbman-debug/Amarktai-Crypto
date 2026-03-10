import { renderToStaticMarkup } from 'react-dom/server';
import SiteFooter from './SiteFooter';

test('renders Amarktai Crypto copyright footer', () => {
  const year = new Date().getFullYear();
  const html = renderToStaticMarkup(<SiteFooter />);
  expect(html).toContain(`© ${year}`);
  expect(html).toContain('Amarkt');
  expect(html).toContain('AI');
  expect(html).toContain('Crypto');
  expect(html).toContain('Personal use only');
});

test('footer does not show any build metadata', () => {
  const html = renderToStaticMarkup(<SiteFooter />);
  expect(html).not.toContain('Build');
  expect(html).not.toContain('Tag');
  expect(html).not.toContain('untagged');
  expect(html).not.toContain('unknown');
});
